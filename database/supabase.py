"""Async Supabase REST access with pooled HTTP and cached active themes."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone

import aiohttp

logger = logging.getLogger(__name__)
THEME_COLUMNS = "id,platform,category,name,url,description,is_active,created_at"
THEME_PAGE_SIZE = 500


class SupabaseError(RuntimeError):
    """A safe, non-secret-bearing Supabase access error."""


class SupabaseDB:
    def __init__(self, url: str, key: str, cache_ttl_seconds: float = 60):
        self.url = url.rstrip("/")
        self.key = key
        self.session: aiohttp.ClientSession | None = None
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._theme_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
        self._theme_locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def initialize(self) -> None:
        if self.session is not None and not self.session.closed:
            return
        timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=7)
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=20, keepalive_timeout=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        # Fail early if credentials or schema are wrong.
        await self._request("GET", "themes", params={"select": "id", "limit": "1"})

    async def _request(self, method: str, table: str, *, params=None, json=None, prefer=None):
        if self.session is None or self.session.closed:
            raise SupabaseError("Supabase client is not initialized")
        headers = {"Prefer": prefer} if prefer else None
        url = f"{self.url}/rest/v1/{table}"
        started = time.perf_counter()
        try:
            async with self.session.request(method, url, params=params, json=json, headers=headers) as response:
                body = await response.text()
                if response.status >= 400:
                    logger.warning("Supabase request failed: table=%s method=%s status=%s duration_ms=%.1f",
                                   table, method, response.status, (time.perf_counter() - started) * 1000)
                    raise SupabaseError(f"Supabase {table} request failed (HTTP {response.status})")
                if not body:
                    return []
                import json as json_module
                try:
                    return json_module.loads(body)
                except ValueError:
                    return body
        except SupabaseError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise SupabaseError(f"Supabase {table} request failed: {type(exc).__name__}") from exc
        finally:
            logger.info("Supabase request: table=%s method=%s duration_ms=%.1f",
                        table, method, (time.perf_counter() - started) * 1000)

    async def touch(self, user) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "telegram_id": user.id, "username": user.username, "first_name": user.first_name,
            "last_name": user.last_name, "language_code": user.language_code, "last_seen_at": now,
        }
        existing = await self._request(
            "GET", "users",
            params={"telegram_id": f"eq.{user.id}", "select": "telegram_id", "limit": "1"},
        )
        if existing:
            await self._request("PATCH", "users", params={"telegram_id": f"eq.{user.id}"},
                                json=payload, prefer="return=minimal")
        else:
            payload["first_seen_at"] = now
            await self._request("POST", "users", json=payload, prefer="return=minimal")
        # One upsert keeps the state row available without an existence-check round trip.
        await self._request(
            "POST", "user_states",
            json={"telegram_id": user.id, "last_activity": now},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def _ensure_state(self, user_id: int) -> None:
        await self._request(
            "POST", "user_states",
            json={"telegram_id": user_id, "last_activity": datetime.now(timezone.utc).isoformat()},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def _state_update(self, user_id: int, values: dict) -> None:
        # PostgREST upsert inserts missing state rows and updates only supplied fields.
        payload = dict(values)
        payload["telegram_id"] = user_id
        payload["last_activity"] = datetime.now(timezone.utc).isoformat()
        await self._request("POST", "user_states", json=payload,
                            prefer="resolution=merge-duplicates,return=minimal")

    async def set_os(self, user_id: int, os_name: str) -> None:
        if os_name not in {"iOS", "Android"}:
            raise ValueError("Unsupported OS")
        await self._state_update(user_id, {
            "selected_os": os_name, "selected_category": None, "current_theme_id": None
        })

    async def set_category(self, user_id: int, category: str) -> None:
        if category not in {"Dark", "Soft", "Anime", "Boshqa"}:
            raise ValueError("Unsupported category")
        await self._state_update(user_id, {"selected_category": category, "current_theme_id": None})

    async def set_theme(self, user_id: int, theme_id: str) -> None:
        await self._state_update(user_id, {"current_theme_id": theme_id})

    async def get_state(self, user_id: int) -> dict | None:
        rows = await self._request("GET", "user_states", params={
            "telegram_id": f"eq.{user_id}",
            "select": "telegram_id,selected_os,selected_category,current_theme_id,last_activity",
            "limit": "1",
        })
        if not rows:
            return None
        row = rows[0]
        try:
            last = datetime.fromisoformat(row["last_activity"].replace("Z", "+00:00"))
            if last < datetime.now(timezone.utc) - timedelta(seconds=3600):
                await self._request("DELETE", "user_states", params={"telegram_id": f"eq.{user_id}"},
                                    prefer="return=minimal")
                return None
        except (ValueError, TypeError, KeyError):
            return None
        # Do not PATCH on every read. Meaningful state changes/touch update activity.
        return row

    async def cleanup_expired(self, ttl_seconds: int = 3600) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)).isoformat()
        rows = await self._request("GET", "user_states", params={
            "select": "telegram_id", "last_activity": f"lt.{cutoff}", "limit": "1000"
        })
        if not rows:
            return 0
        ids = [str(row["telegram_id"]) for row in rows]
        await self._request("DELETE", "user_states", params={"telegram_id": f"in.({','.join(ids)})"},
                            prefer="return=minimal")
        return len(ids)

    async def list_themes(self, *, platform=None, category=None, active_only=False, offset=0, limit=10):
        params = {"select": "*", "order": "created_at.desc", "offset": str(offset), "limit": str(limit)}
        if platform:
            params["platform"] = f"eq.{platform}"
        if category:
            params["category"] = f"eq.{category}"
        if active_only:
            params["is_active"] = "eq.true"
        return await self._request("GET", "themes", params=params)

    async def get_theme(self, theme_id: str):
        rows = await self._request("GET", "themes", params={
            "id": f"eq.{theme_id}", "select": "*", "limit": "1"
        })
        return rows[0] if rows else None

    def invalidate_theme_cache(self) -> None:
        self._theme_cache.clear()

    async def _active_themes(self, platform: str, category: str) -> list[dict]:
        key = (platform, category)
        now = time.monotonic()
        cached = self._theme_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

        lock = self._theme_locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = self._theme_cache.get(key)
            if cached and cached[0] > now:
                return cached[1]
            try:
                rows: list[dict] = []
                offset = 0
                while True:
                    page = await self._request("GET", "themes", params={
                        "select": THEME_COLUMNS,
                        "platform": f"eq.{platform}",
                        "category": f"eq.{category}",
                        "is_active": "eq.true",
                        "order": "id.asc",
                        "offset": str(offset),
                        "limit": str(THEME_PAGE_SIZE),
                    })
                    rows.extend(page)
                    if len(page) < THEME_PAGE_SIZE:
                        break
                    offset += len(page)
                self._theme_cache[key] = (time.monotonic() + self.cache_ttl_seconds, rows)
                return rows
            except SupabaseError:
                # Use stale data when available rather than turning a temporary outage into an empty list.
                if cached:
                    logger.warning("Using stale theme cache after Supabase refresh failure")
                    return cached[1]
                raise

    async def get_random(self, platform: str, category: str, previous_id=None):
        rows = await self._active_themes(platform, category)
        if not rows:
            return None
        choices = [item for item in rows if item["id"] != previous_id] or rows
        return random.choice(choices)

    async def add_theme(self, theme: dict):
        rows = await self._request("POST", "themes", json=theme, prefer="return=representation")
        if rows:
            self.invalidate_theme_cache()
        return rows[0] if rows else None

    async def update_theme(self, theme_id: str, values: dict):
        rows = await self._request("PATCH", "themes", params={"id": f"eq.{theme_id}"},
                                   json=values, prefer="return=representation")
        if not rows:
            raise SupabaseError("Theme was not updated; it may have been deleted.")
        verified = await self.get_theme(theme_id)
        if not verified or any(verified.get(k) != v for k, v in values.items()):
            raise SupabaseError("Theme update could not be verified.")
        self.invalidate_theme_cache()
        return verified

    async def delete_theme(self, theme_id: str):
        # Clear the optional state reference first so FK constraints cannot strand deletion.
        await self._request("PATCH", "user_states", params={"current_theme_id": f"eq.{theme_id}"},
                            json={"current_theme_id": None}, prefer="return=minimal")
        rows = await self._request("DELETE", "themes",
                                   params={"id": f"eq.{theme_id}", "select": "id"},
                                   prefer="return=representation")
        if rows:
            self.invalidate_theme_cache()
        return bool(rows)

    async def count(self, table: str, *, active_only=False) -> int:
        if table not in {"users", "themes"}:
            raise ValueError("Unsupported count table")
        total = 0
        offset = 0
        while True:
            params = {"select": "telegram_id" if table == "users" else "id",
                      "offset": str(offset), "limit": "1000"}
            if active_only:
                params["is_active"] = "eq.true"
            rows = await self._request("GET", table, params=params)
            total += len(rows)
            if len(rows) < 1000:
                return total
            offset += len(rows)

    async def user_ids(self) -> list[int]:
        result = []
        offset = 0
        while True:
            rows = await self._request("GET", "users", params={
                "select": "telegram_id", "order": "telegram_id",
                "offset": str(offset), "limit": "1000",
            })
            result.extend(int(row["telegram_id"]) for row in rows)
            if len(rows) < 1000:
                break
            offset += len(rows)
        return result

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
