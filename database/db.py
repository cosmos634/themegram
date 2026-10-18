"""SQLite-backed temporary per-user state."""
import asyncio
import time
from pathlib import Path
import aiosqlite


class UserStateDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute("""CREATE TABLE IF NOT EXISTS user_states (
                    user_id INTEGER PRIMARY KEY, selected_os TEXT,
                    selected_category TEXT, current_theme_id TEXT,
                    last_activity REAL NOT NULL)""")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_state_activity ON user_states(last_activity)")
                await db.execute("DELETE FROM user_states WHERE last_activity < ?", (time.time() - 3600,))
                await db.commit()

    async def touch(self, user_id: int) -> None:
        now = time.time()
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute("""INSERT INTO user_states(user_id,last_activity) VALUES(?,?)
                    ON CONFLICT(user_id) DO UPDATE SET last_activity=excluded.last_activity""", (user_id, now))
                await db.commit()

    async def set_os(self, user_id: int, os_name: str) -> None:
        if os_name not in {"iOS", "Android"}:
            raise ValueError("Unsupported OS")
        now = time.time()
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute("""INSERT INTO user_states(user_id,selected_os,last_activity)
                    VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                    selected_os=excluded.selected_os, selected_category=NULL,
                    current_theme_id=NULL,last_activity=excluded.last_activity""", (user_id, os_name, now))
                await db.commit()

    async def set_category(self, user_id: int, category: str) -> None:
        if category not in {"Dark", "Soft", "Anime", "Boshqa"}:
            raise ValueError("Unsupported category")
        now = time.time()
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute("""INSERT INTO user_states(user_id,selected_category,last_activity)
                    VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                    selected_category=excluded.selected_category,current_theme_id=NULL,
                    last_activity=excluded.last_activity""", (user_id, category, now))
                await db.commit()

    async def set_theme(self, user_id: int, theme_id: str) -> None:
        now = time.time()
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute("""INSERT INTO user_states(user_id,current_theme_id,last_activity)
                    VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                    current_theme_id=excluded.current_theme_id,last_activity=excluded.last_activity""",
                    (user_id, theme_id, now))
                await db.commit()

    async def get_state(self, user_id: int) -> dict | None:
        now = time.time()
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM user_states WHERE user_id=? AND last_activity>=?",
                                          (user_id, now - 3600))
                row = await cursor.fetchone()
                if row is None:
                    await db.execute("DELETE FROM user_states WHERE user_id=?", (user_id,))
                    await db.commit()
                    return None
                await db.execute("UPDATE user_states SET last_activity=? WHERE user_id=?", (now, user_id))
                await db.commit()
                return dict(row)

    async def cleanup_expired(self, ttl_seconds: int = 3600) -> int:
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                cursor = await db.execute("DELETE FROM user_states WHERE last_activity < ?",
                                          (time.time() - ttl_seconds,))
                await db.commit()
                return cursor.rowcount

    async def close(self) -> None:
        return None
