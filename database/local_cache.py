"""SQLite-backed local cache for user profiles and temporary user state."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


class LocalStateCache:
    """Small synchronous SQLite cache; each operation is a short local transaction."""

    def __init__(self, path: str | None = None):
        configured = path or os.getenv("STATE_CACHE_PATH", "themegram_cache.sqlite3")
        self.path = str(Path(configured))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=3000")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cached_users (
                telegram_id INTEGER PRIMARY KEY,
                profile_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                dirty INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS cached_states (
                telegram_id INTEGER PRIMARY KEY,
                state_json TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                dirty INTEGER NOT NULL DEFAULT 0
            );
        """)
        self.conn.commit()

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT profile_json, first_seen_at FROM cached_users WHERE telegram_id=?", (user_id,)
        ).fetchone()
        if not row:
            return None
        profile = json.loads(row["profile_json"])
        profile["first_seen_at"] = row["first_seen_at"]
        return profile

    def touch_user(self, profile: dict[str, Any], now: str) -> None:
        user_id = int(profile["telegram_id"])
        existing = self.get_user(user_id) or {}
        first_seen = existing.get("first_seen_at") or profile.get("first_seen_at") or now
        # Merge rather than replace: language and first_source must survive normal /start calls.
        merged = {**existing, **profile}
        merged["language"] = profile.get("language") or existing.get("language")
        merged["first_source"] = existing.get("first_source") or profile.get("first_source") or "unknown"
        self.conn.execute(
            """INSERT INTO cached_users(telegram_id,profile_json,first_seen_at,dirty)
               VALUES(?,?,?,1)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 profile_json=excluded.profile_json, dirty=1""",
            (user_id, json.dumps(merged, ensure_ascii=False), first_seen),
        )
        self.conn.commit()

    def set_user_language(self, user_id: int, language: str) -> None:
        profile = self.get_user(user_id)
        if profile is None:
            raise KeyError(f"Unknown cached user: {user_id}")
        profile["language"] = language
        first_seen = profile.pop("first_seen_at", None)
        self.conn.execute(
            "UPDATE cached_users SET profile_json=?, dirty=1 WHERE telegram_id=?",
            (json.dumps(profile, ensure_ascii=False), user_id),
        )
        self.conn.commit()

    def get_state(self, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT state_json FROM cached_states WHERE telegram_id=?", (user_id,)
        ).fetchone()
        return json.loads(row["state_json"]) if row else None

    def save_state(self, user_id: int, state: dict[str, Any], *, dirty: bool) -> None:
        last_activity = str(state["last_activity"])
        self.conn.execute(
            """INSERT INTO cached_states(telegram_id,state_json,last_activity,dirty)
               VALUES(?,?,?,?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 state_json=excluded.state_json,
                 last_activity=excluded.last_activity,
                 dirty=CASE WHEN excluded.dirty=1 THEN 1 ELSE cached_states.dirty END""",
            (user_id, json.dumps(state, ensure_ascii=False), last_activity, int(dirty)),
        )
        self.conn.commit()

    def delete_state(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM cached_states WHERE telegram_id=?", (user_id,))
        self.conn.commit()

    def update_state(self, user_id: int, values: dict[str, Any], now: str) -> dict[str, Any]:
        state = self.get_state(user_id) or {
            "telegram_id": user_id, "selected_os": None,
            "selected_category": None, "current_theme_id": None,
        }
        state.update(values)
        state["telegram_id"] = user_id
        state["last_activity"] = now
        self.save_state(user_id, state, dirty=True)
        return state

    def mark_state_activity(self, user_id: int, now: str) -> None:
        state = self.get_state(user_id)
        if state is not None:
            state["last_activity"] = now
            self.save_state(user_id, state, dirty=True)

    def dirty_users(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT telegram_id,profile_json,first_seen_at FROM cached_users WHERE dirty=1"
        ).fetchall()
        result = []
        for row in rows:
            profile = json.loads(row["profile_json"])
            profile["first_seen_at"] = row["first_seen_at"]
            result.append(profile)
        return result

    def mark_users_clean(self, snapshots: list[dict[str, Any]]) -> None:
        """Clear dirty only if the row still matches the uploaded snapshot."""
        if snapshots:
            self.conn.executemany(
                """UPDATE cached_users SET dirty=0
                   WHERE telegram_id=? AND profile_json=? AND first_seen_at=? AND dirty=1""",
                [(int(row["telegram_id"]),
                  json.dumps({k: v for k, v in row.items() if k != "first_seen_at"}, ensure_ascii=False),
                  str(row["first_seen_at"])) for row in snapshots],
            )
            self.conn.commit()

    def dirty_states(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT state_json FROM cached_states WHERE dirty=1").fetchall()
        return [json.loads(row["state_json"]) for row in rows]

    def mark_states_clean(self, snapshots: list[dict[str, Any]]) -> None:
        """Do not clear a newer edit that happened while an older snapshot uploaded."""
        if snapshots:
            self.conn.executemany(
                """UPDATE cached_states SET dirty=0
                   WHERE telegram_id=? AND state_json=? AND dirty=1""",
                [(int(row["telegram_id"]), json.dumps(row, ensure_ascii=False)) for row in snapshots],
            )
            self.conn.commit()

    def all_states(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT state_json FROM cached_states").fetchall()
        return [json.loads(row["state_json"]) for row in rows]

    def merge_remote_states(self, states: list[dict[str, Any]]) -> None:
        for state in states:
            user_id = int(state["telegram_id"])
            existing = self.conn.execute(
                "SELECT dirty FROM cached_states WHERE telegram_id=?", (user_id,)
            ).fetchone()
            if existing and existing["dirty"]:
                continue
            self.save_state(user_id, state, dirty=False)

    def expire_states(self, cutoff: str) -> int:
        cursor = self.conn.execute(
            "DELETE FROM cached_states WHERE last_activity < ? AND dirty=0", (cutoff,)
        )
        self.conn.commit()
        return cursor.rowcount

    def user_ids(self) -> list[int]:
        rows = self.conn.execute("SELECT telegram_id FROM cached_users").fetchall()
        return [int(row["telegram_id"]) for row in rows]

    def close(self) -> None:
        self.conn.close()
