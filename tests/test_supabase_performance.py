import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from database.local_cache import LocalStateCache
from database.supabase import SupabaseDB, SupabaseError


class CacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SupabaseDB("https://example.supabase.co", "fake")
        self.db.local.close()
        self.db.local = LocalStateCache(os.path.join(self.tmp.name, "state.sqlite3"))

    def tearDown(self):
        self.db.local.close()
        self.tmp.cleanup()

    async def test_theme_selection_uses_only_warmed_cache(self):
        self.db._theme_cache[("iOS", "Dark")] = [{"id": "a"}, {"id": "b"}]
        self.db._request = AsyncMock(side_effect=AssertionError("user request must not query Supabase"))
        with patch("database.supabase.random.choice", side_effect=lambda rows: rows[0]) as choice:
            self.assertEqual((await self.db.get_random("iOS", "Dark", "a"))["id"], "b")
        self.assertEqual(choice.call_args.args[0], [{"id": "b"}])
        self.db._request.assert_not_awaited()

    async def test_theme_refresh_loads_50_for_each_group_and_swaps_atomically(self):
        db = self.db
        db._request = AsyncMock(return_value=[{"id": "theme"}])
        await db.refresh_theme_cache()
        self.assertEqual(len(db._theme_cache), 8)
        self.assertEqual(db._request.await_count, 8)
        self.assertTrue(all(call.kwargs["params"]["limit"] == "50"
                            for call in db._request.await_args_list))
        old_cache = db._theme_cache
        db._request = AsyncMock(side_effect=[[], SupabaseError("offline")])
        with self.assertRaises(SupabaseError):
            await db.refresh_theme_cache()
        self.assertIs(db._theme_cache, old_cache)

    async def test_state_updates_are_local_and_merge_fields(self):
        await self.db.set_os(42, "iOS")
        await self.db.set_category(42, "Dark")
        await self.db.set_theme(42, "theme-1")
        state = self.db.local.get_state(42)
        self.assertEqual(state["selected_os"], "iOS")
        self.assertEqual(state["selected_category"], "Dark")
        self.assertEqual(state["current_theme_id"], "theme-1")

    async def test_missing_state_loads_from_supabase_once_then_uses_sqlite(self):
        remote = {"telegram_id": 7, "selected_os": "Android", "selected_category": "Soft",
                  "current_theme_id": None, "last_activity": datetime.now(timezone.utc).isoformat()}
        self.db._request = AsyncMock(return_value=[remote])
        self.assertEqual((await self.db.get_state(7))["selected_os"], "Android")
        self.assertEqual((await self.db.get_state(7))["selected_os"], "Android")
        self.db._request.assert_awaited_once()

    async def test_sync_failure_keeps_dirty_local_state(self):
        await self.db.set_os(99, "iOS")
        self.db._request = AsyncMock(side_effect=SupabaseError("offline"))
        with self.assertRaises(SupabaseError):
            await self.db.sync_user_state()
        self.assertTrue(self.db.local.dirty_states())

    async def test_previous_theme_excluded(self):
        self.db._theme_cache[("Android", "Anime")] = [{"id": "a"}, {"id": "b"}]
        with patch("database.supabase.random.choice", side_effect=lambda rows: rows[0]):
            self.assertEqual((await self.db.get_random("Android", "Anime", "a"))["id"], "b")


if __name__ == "__main__":
    unittest.main()
