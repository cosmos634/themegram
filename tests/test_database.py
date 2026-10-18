import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from database.db import UserStateDB


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = UserStateDB(Path(self.tempdir.name) / "test.sqlite3")
        await self.db.initialize()

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def test_users_are_isolated(self):
        await self.db.set_os(101, "iOS")
        await self.db.set_os(202, "Android")
        first = await self.db.get_state(101)
        second = await self.db.get_state(202)
        self.assertEqual(first["selected_os"], "iOS")
        self.assertEqual(second["selected_os"], "Android")

    async def test_state_updates(self):
        await self.db.set_os(101, "Android")
        await self.db.set_category(101, "Anime")
        state = await self.db.get_state(101)
        self.assertEqual(state["selected_os"], "Android")
        self.assertEqual(state["selected_category"], "Anime")

    async def test_expired_state_is_removed(self):
        await self.db.touch(101)
        async with __import__("aiosqlite").connect(self.db.path) as conn:
            await conn.execute("UPDATE user_states SET last_activity=?", (time.time() - 4000,))
            await conn.commit()
        deleted = await self.db.cleanup_expired(3600)
        self.assertEqual(deleted, 1)
        self.assertIsNone(await self.db.get_state(101))


if __name__ == "__main__":
    unittest.main()
