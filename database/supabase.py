"""Async Supabase access with an hourly theme cache and SQLite-backed user state."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone

import aiohttp

from database.local_cache import LocalStateCache

log = logging.getLogger(__name__)
THEME_FIELDS = "id,name,description,url,platform,category,is_active,created_at"
PLATFORMS = ("iOS", "Android")
CATEGORIES = ("Dark", "Soft", "Anime", "Boshqa")
THEMES_PER_GROUP = 50
SYNC_INTERVAL_SECONDS = 3600


class SupabaseError(RuntimeError):
    pass


class SupabaseDB:
    def __init__(self, url: str, key: str, *, theme_cache_ttl: int | None = None, page_size: int = 500):
        self.url, self.key = url.rstrip("/"), key
        self.session: aiohttp.ClientSession | None = None
        self.page_size = max(1, min(int(page_size), 1000))
        self.theme_cache_ttl = SYNC_INTERVAL_SECONDS
        self._theme_cache: dict[tuple[str, str], list[dict]] = {}
        self._theme_refresh_lock = asyncio.Lock()
        self.local = LocalStateCache()
        self._last_theme_refresh = 0.0
        self._last_state_sync = 0.0

    async def initialize(self) -> None:
        if self.session is not None and not self.session.closed:
            return
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15, connect=5, sock_read=10),
            connector=aiohttp.TCPConnector(limit=30, limit_per_host=20, keepalive_timeout=30),
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json", "Accept": "application/json"})
        try:
            await self._request("GET", "themes", params={"select": "id", "limit": "1"})
            # Warm all eight groups once before serving requests.
            await self.refresh_theme_cache()
            await self.sync_user_state()
        except Exception:
            await self.close()
            raise

    async def _request(self, method: str, table: str, *, params=None, json=None, prefer=None):
        if self.session is None or self.session.closed:
            raise SupabaseError("Supabase client is not initialized")
        started = time.perf_counter()
        try:
            async with self.session.request(
                method, f"{self.url}/rest/v1/{table}", params=params, json=json,
                headers={"Prefer": prefer} if prefer else None
            ) as response:
                body = await response.text()
                log.info("supabase_request method=%s table=%s status=%s duration_ms=%.1f",
                         method, table, response.status, (time.perf_counter()-started)*1000)
                if response.status >= 400:
                    raise SupabaseError(f"Supabase {table} request failed (HTTP {response.status})")
                if not body:
                    return []
                try:
                    import json as json_module
                    return json_module.loads(body)
                except ValueError:
                    return body
        except SupabaseError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("supabase_request_failed method=%s table=%s error=%s duration_ms=%.1f",
                        method, table, type(exc).__name__, (time.perf_counter()-started)*1000)
            raise SupabaseError(f"Supabase {table} request failed: {type(exc).__name__}") from exc

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def touch(self, user, first_source: str = "direct") -> None:
        now = self._now()
        cached = self.local.get_user(user.id)
        if cached is None:
            # A cold SQLite cache must hydrate the existing remote profile before writing,
            # otherwise an old user's language/attribution could be overwritten by nulls.
            rows = await self._request("GET", "users", params={
                "telegram_id": f"eq.{user.id}", "select": "*", "limit": "1"
            })
            remote = rows[0] if rows else None
            if remote:
                profile = {
                    **remote,
                    "first_source": remote.get("first_source") or "unknown",
                }
            else:
                profile = {"language": None, "first_source": first_source or "direct"}
        else:
            profile = cached
        profile.update({
            "telegram_id": user.id, "username": user.username,
            "first_name": user.first_name, "last_name": user.last_name,
            "language_code": user.language_code, "last_seen_at": now,
        })
        profile["first_source"] = profile.get("first_source") or "unknown"
        self.local.touch_user(profile, now)
        state = self.local.get_state(user.id)
        if state:
            self.local.mark_state_activity(user.id, now)
        else:
            # First-time/missing state is the only normal interaction path that reads Supabase.
            await self.get_state(user.id)

    async def set_language(self, user_id: int, language: str) -> None:
        if language not in {"uz", "ru"}:
            raise ValueError("Unsupported language")
        if self.local.get_user(user_id) is None:
            raise SupabaseError("User profile is not cached")
        self.local.set_user_language(user_id, language)

    def get_language(self, user_id: int) -> str | None:
        profile = self.local.get_user(user_id)
        return profile.get("language") if profile else None

    async def traffic_analytics(self) -> dict:
        """Aggregate attribution and language counts from the canonical users table."""
        sources: dict[str, int] = {}
        languages = {"uz": 0, "ru": 0, "unset": 0}
        total = offset = 0
        while True:
            rows = await self._request("GET", "users", params={
                "select": "language,first_source", "order": "telegram_id",
                "offset": str(offset), "limit": str(self.page_size)
            })
            if not isinstance(rows, list):
                raise SupabaseError("Unexpected analytics response")
            for row in rows:
                total += 1
                source = row.get("first_source") or "unknown"
                sources[source] = sources.get(source, 0) + 1
                language = row.get("language")
                bucket = language if language in {"uz", "ru"} else "unset"
                languages[bucket] += 1
            if len(rows) < self.page_size:
                break
            offset += len(rows)
        return {"total": total, "sources": sources, "languages": languages}

    async def _state_update(self, user_id: int, values: dict) -> None:
        self.local.update_state(user_id, values, self._now())

    async def set_os(self, user_id: int, os_name: str) -> None:
        if os_name not in PLATFORMS:
            raise ValueError("Unsupported OS")
        await self._state_update(user_id, {
            "selected_os": os_name, "selected_category": None, "current_theme_id": None
        })

    async def set_category(self, user_id: int, category: str) -> None:
        if category not in CATEGORIES:
            raise ValueError("Unsupported category")
        await self._state_update(user_id, {"selected_category": category, "current_theme_id": None})

    async def set_theme(self, user_id: int, theme_id: str) -> None:
        await self._state_update(user_id, {"current_theme_id": theme_id})

    async def get_state(self, user_id: int) -> dict | None:
        state = self.local.get_state(user_id)
        if state:
            try:
                last = datetime.fromisoformat(state["last_activity"].replace("Z", "+00:00"))
                if last < datetime.now(timezone.utc) - timedelta(seconds=3600):
                    self.local.delete_state(user_id)
                    return None
            except (ValueError, TypeError, KeyError, AttributeError):
                self.local.delete_state(user_id)
                return None
            self.local.mark_state_activity(user_id, self._now())
            return self.local.get_state(user_id)

        rows = await self._request("GET", "user_states", params={
            "telegram_id": f"eq.{user_id}",
            "select": "telegram_id,selected_os,selected_category,current_theme_id,last_activity",
            "limit": "1"})
        if not rows:
            return None
        state = rows[0]
        try:
            last = datetime.fromisoformat(state["last_activity"].replace("Z", "+00:00"))
            if last < datetime.now(timezone.utc) - timedelta(seconds=3600):
                return None
        except (ValueError, TypeError, KeyError, AttributeError):
            return None
        self.local.save_state(user_id, state, dirty=False)
        return state

    async def cleanup_expired(self, ttl_seconds: int = 3600) -> int:
        cutoff = (datetime.now(timezone.utc)-timedelta(seconds=ttl_seconds)).isoformat()
        return self.local.expire_states(cutoff)

    async def sync_user_state(self) -> None:
        """Push dirty local rows, then merge remote state without overwriting local edits."""
        # Dirty flags are cleared only after a successful remote write.
        users = self.local.dirty_users()
        if users:
            await self._request("POST", "users", params={"on_conflict": "telegram_id"},
                                json=users, prefer="resolution=merge-duplicates,return=minimal")
            self.local.mark_users_clean(users)

        states = self.local.dirty_states()
        if states:
            await self._request("POST", "user_states", params={"on_conflict": "telegram_id"},
                                json=states, prefer="resolution=merge-duplicates,return=minimal")
            self.local.mark_states_clean(states)

        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat()
        await self._request("DELETE", "user_states", params={"last_activity": f"lt.{cutoff}"})
        offset = 0
        while True:
            rows = await self._request("GET", "user_states", params={
                "select": "telegram_id,selected_os,selected_category,current_theme_id,last_activity",
                "order": "telegram_id", "offset": str(offset), "limit": str(self.page_size)})
            if not isinstance(rows, list):
                raise SupabaseError("Unexpected response while synchronizing user states")
            self.local.merge_remote_states(rows)
            if len(rows) < self.page_size:
                break
            offset += len(rows)
        self._last_state_sync = time.monotonic()
        log.info("user_state_sync complete dirty_users=%s dirty_states=%s", len(users), len(states))

    async def sync_loop(self, interval_seconds: int = SYNC_INTERVAL_SECONDS) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await self.sync_user_state()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Local dirty rows remain marked dirty and are retried next hour.
                log.exception("Hourly user-state sync failed; local changes retained")

    async def track_event(self, user_id: int, event_name: str, metadata: dict | None = None) -> None:
        """Record a small product-analytics event; failures are logged, not user-facing."""
        import re
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", event_name):
            raise ValueError("Invalid event name")
        payload = {"telegram_id": int(user_id), "event_name": event_name,
                   "metadata": metadata or {}}
        try:
            await self._request("POST", "themegram_events", json=payload,
                                prefer="return=minimal")
        except SupabaseError:
            log.warning("event_tracking_failed event=%s", event_name)

    async def add_favorite(self, user_id: int, theme_id: str) -> bool:
        rows = await self._request("POST", "themegram_favorites",
            params={"on_conflict": "telegram_id,theme_id"},
            json={"telegram_id": int(user_id), "theme_id": str(theme_id)},
            prefer="resolution=ignore-duplicates,return=representation")
        return bool(rows)

    async def remove_favorite(self, user_id: int, theme_id: str) -> None:
        await self._request("DELETE", "themegram_favorites", params={
            "telegram_id": f"eq.{int(user_id)}", "theme_id": f"eq.{theme_id}"})

    async def list_favorites(self, user_id: int) -> list[dict]:
        rows = await self._request("GET", "themegram_favorites", params={
            "select": "theme_id,created_at", "telegram_id": f"eq.{int(user_id)}",
            "order": "created_at.desc", "limit": "100"})
        result = []
        for row in rows:
            theme = await self.get_theme(str(row["theme_id"]))
            if theme and theme.get("is_active", True):
                result.append(theme)
        return result

    async def search_themes(self, query: str, *, platform: str | None = None,
                            category: str | None = None, limit: int = 10) -> list[dict]:
        term = query.strip()
        if not term or len(term) > 80:
            return []
        params = {"select": THEME_FIELDS, "is_active": "eq.true",
                  "or": f"(name.ilike.*{term}*,description.ilike.*{term}*)",
                  "order": "created_at.desc", "limit": str(max(1, min(limit, 20)))}
        if platform in PLATFORMS:
            params["platform"] = f"eq.{platform}"
        if category in CATEGORIES:
            params["category"] = f"eq.{category}"
        rows = await self._request("GET", "themes", params=params)
        return rows if isinstance(rows, list) else []

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
        rows = await self._request("GET", "themes", params={"id": f"eq.{theme_id}", "select": "*", "limit": "1"})
        return rows[0] if rows else None

    async def refresh_theme_cache(self) -> None:
        async with self._theme_refresh_lock:
            refreshed: dict[tuple[str, str], list[dict]] = {}
            for platform in PLATFORMS:
                for category in CATEGORIES:
                    rows = await self._request("GET", "themes", params={
                        "select": THEME_FIELDS, "platform": f"eq.{platform}",
                        "category": f"eq.{category}", "is_active": "eq.true",
                        "order": "created_at.desc", "limit": str(THEMES_PER_GROUP)})
                    if not isinstance(rows, list):
                        raise SupabaseError("Unexpected response while refreshing theme cache")
                    refreshed[(platform, category)] = rows[:THEMES_PER_GROUP]
            # Swap only after all groups were loaded; on failure the old cache survives.
            self._theme_cache = refreshed
            self._last_theme_refresh = time.monotonic()
            log.info("theme_cache refreshed groups=%s themes=%s",
                     len(refreshed), sum(map(len, refreshed.values())))

    async def theme_refresh_loop(self, interval_seconds: int = SYNC_INTERVAL_SECONDS) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await self.refresh_theme_cache()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Hourly theme refresh failed; previous cache retained")

    def invalidate_theme_cache(self) -> None:
        # Preserve the last good snapshot until the next successful background refresh.
        self._last_theme_refresh = 0.0

    async def _refresh_after_admin_change(self) -> None:
        try:
            await self.refresh_theme_cache()
        except SupabaseError:
            # The admin write already succeeded. Do not report it as failed;
            # keep serving the last good cache and retry during the hourly refresh.
            log.exception("Theme cache refresh after admin change failed; stale snapshot retained")

    async def get_random(self, platform: str, category: str, previous_id=None):
        rows = self._theme_cache.get((platform, category), [])
        if not rows:
            return None
        choices = [r for r in rows if str(r.get("id")) != str(previous_id)] or rows
        return random.choice(choices)

    async def add_theme(self, theme: dict):
        rows = await self._request("POST", "themes", json=theme, prefer="return=representation")
        if rows:
            await self._refresh_after_admin_change()
            return rows[0]
        return None

    async def update_theme(self, theme_id: str, values: dict):
        rows = await self._request("PATCH", "themes", params={"id": f"eq.{theme_id}"},
                                   json=values, prefer="return=representation")
        if not rows:
            raise SupabaseError("Theme was not updated; it may have been deleted.")
        verified = await self.get_theme(theme_id)
        if not verified or any(verified.get(k) != v for k, v in values.items()):
            raise SupabaseError("Theme update could not be verified.")
        await self._refresh_after_admin_change()
        return verified

    async def delete_theme(self, theme_id: str):
        await self._request("PATCH", "user_states", params={"current_theme_id": f"eq.{theme_id}"},
                            json={"current_theme_id": None}, prefer="return=minimal")
        rows = await self._request("DELETE", "themes", params={"id": f"eq.{theme_id}", "select": "id"},
                                   prefer="return=representation")
        if rows:
            await self._refresh_after_admin_change()
        return bool(rows)

    async def count(self, table: str, *, active_only=False) -> int:
        if table not in {"users", "themes"}:
            raise ValueError("Unsupported count table")
        total = offset = 0
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
                "offset": str(offset), "limit": "1000"})
            result.extend(int(r["telegram_id"]) for r in rows)
            if len(rows) < 1000:
                return result
            offset += len(rows)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        self.local.close()
