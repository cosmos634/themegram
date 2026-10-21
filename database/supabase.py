"""Async Supabase REST access; service-role key stays server-side."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import aiohttp


class SupabaseError(RuntimeError):
    pass


class SupabaseDB:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key
        self.session: aiohttp.ClientSession | None = None

    async def initialize(self) -> None:
        timeout = aiohttp.ClientTimeout(total=15)
        self.session = aiohttp.ClientSession(timeout=timeout, headers={
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        # Fail early if credentials or schema are wrong.
        await self._request("GET", "themes", params={"select": "id", "limit": "1"})

    async def _request(self, method: str, table: str, *, params=None, json=None, prefer=None):
        if self.session is None:
            raise SupabaseError("Supabase client is not initialized")
        headers = {"Prefer": prefer} if prefer else None
        url = f"{self.url}/rest/v1/{table}"
        try:
            async with self.session.request(method, url, params=params, json=json, headers=headers) as response:
                body = await response.text()
                if response.status >= 400:
                    # Never include headers/credentials in error messages.
                    raise SupabaseError(f"Supabase {table} request failed (HTTP {response.status}): {body[:500]}")
                if not body:
                    return []
                try:
                    import json as json_module
                    return json_module.loads(body)
                except ValueError:
                    return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise SupabaseError(f"Supabase {table} request failed: {type(exc).__name__}") from exc

    async def touch(self, user) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = {"telegram_id": user.id, "username": user.username, "first_name": user.first_name,
                   "last_name": user.last_name, "language_code": user.language_code,
                   "last_seen_at": now}
        existing = await self._request("GET", "users", params={"telegram_id": f"eq.{user.id}", "select": "telegram_id", "limit": "1"})
        if existing:
            await self._request("PATCH", "users", params={"telegram_id": f"eq.{user.id}"}, json=payload, prefer="return=minimal")
        else:
            payload["first_seen_at"] = now
            await self._request("POST", "users", json=payload, prefer="return=minimal")
        await self._request("POST", "user_states", json={"telegram_id": user.id, "last_activity": now},
                            prefer="resolution=merge-duplicates,return=minimal")

    async def _ensure_state(self, user_id: int) -> None:
        await self._request("POST", "user_states", json={
            "telegram_id": user_id, "last_activity": datetime.now(timezone.utc).isoformat()
        }, prefer="resolution=merge-duplicates,return=minimal")

    async def _state_update(self, user_id: int, values: dict) -> None:
        await self._ensure_state(user_id)
        values["last_activity"] = datetime.now(timezone.utc).isoformat()
        await self._request("PATCH", "user_states", params={"telegram_id": f"eq.{user_id}"},
                            json=values, prefer="return=minimal")

    async def set_os(self, user_id: int, os_name: str) -> None:
        if os_name not in {"iOS", "Android"}:
            raise ValueError("Unsupported OS")
        await self._state_update(user_id, {"selected_os": os_name, "selected_category": None, "current_theme_id": None})

    async def set_category(self, user_id: int, category: str) -> None:
        if category not in {"Dark", "Soft", "Anime", "Boshqa"}:
            raise ValueError("Unsupported category")
        await self._state_update(user_id, {"selected_category": category, "current_theme_id": None})

    async def set_theme(self, user_id: int, theme_id: str) -> None:
        await self._state_update(user_id, {"current_theme_id": theme_id})

    async def get_state(self, user_id: int) -> dict | None:
        rows = await self._request("GET", "user_states", params={
            "telegram_id": f"eq.{user_id}", "select": "*", "limit": "1"
        })
        if not rows:
            return None
        row = rows[0]
        try:
            last = datetime.fromisoformat(row["last_activity"].replace("Z", "+00:00"))
            if last < datetime.now(timezone.utc) - timedelta(seconds=3600):
                await self._request("DELETE", "user_states", params={"telegram_id": f"eq.{user_id}"})
                return None
        except (ValueError, TypeError, KeyError):
            return None
        await self._request("PATCH", "user_states", params={"telegram_id": f"eq.{user_id}"},
                            json={"last_activity": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
        return row

    async def cleanup_expired(self, ttl_seconds: int = 3600) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)).isoformat()
        rows = await self._request("GET", "user_states", params={
            "select": "telegram_id", "last_activity": f"lt.{cutoff}", "limit": "1000"
        })
        if not rows:
            return 0
        ids = [str(row["telegram_id"]) for row in rows]
        await self._request("DELETE", "user_states", params={"telegram_id": f"in.({','.join(ids)})"})
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
        rows = await self._request("GET", "themes", params={"id": f"eq.{theme_id}", "select": "*", "limit": "1"})
        return rows[0] if rows else None

    async def get_random(self, platform: str, category: str, previous_id=None):
        rows = await self.list_themes(platform=platform, category=category, active_only=True, limit=1000)
        if not rows:
            return None
        choices = [item for item in rows if item["id"] != previous_id] or rows
        import random
        return random.choice(choices)

    async def add_theme(self, theme: dict):
        rows = await self._request("POST", "themes", json=theme, prefer="return=representation")
        return rows[0] if rows else None

    async def update_theme(self, theme_id: str, values: dict):
        rows = await self._request("PATCH", "themes", params={"id": f"eq.{theme_id}"},
                                   json=values, prefer="return=representation")
        if not rows:
            raise SupabaseError("Theme was not updated; it may have been deleted.")
        verified = await self.get_theme(theme_id)
        if not verified or any(verified.get(k) != v for k, v in values.items()):
            raise SupabaseError("Theme update could not be verified.")
        return verified

    async def delete_theme(self, theme_id: str):
        # Clear the optional state reference first so FK constraints cannot strand deletion.
        await self._request("PATCH", "user_states", params={"current_theme_id": f"eq.{theme_id}"},
                            json={"current_theme_id": None}, prefer="return=minimal")
        rows = await self._request("DELETE", "themes", params={"id": f"eq.{theme_id}", "select": "id"},
                                   prefer="return=representation")
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
            rows = await self._request("GET", "users", params={"select": "telegram_id", "order": "telegram_id", "offset": str(offset), "limit": "1000"})
            result.extend(int(row["telegram_id"]) for row in rows)
            if len(rows) < 1000:
                break
            offset += len(rows)
        return result

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
