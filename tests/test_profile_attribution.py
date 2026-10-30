import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from database.local_cache import LocalStateCache
from database.supabase import SupabaseDB, SupabaseError


class UserProfileCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = LocalStateCache(os.path.join(self.tmp.name, "cache.sqlite3"))

    def tearDown(self):
        self.cache.close()
        self.tmp.cleanup()

    def test_language_and_first_source_persist_without_changing_first_seen(self):
        first_seen = "2026-01-01T00:00:00+00:00"
        self.cache.touch_user({
            "telegram_id": 10, "username": "tester", "language": None,
            "first_source": "instagram", "first_seen_at": first_seen,
        }, first_seen)
        self.cache.save_state(10, {
            "telegram_id": 10, "selected_os": "iOS", "selected_category": "Dark",
            "current_theme_id": "theme-1", "last_activity": first_seen,
        }, dirty=False)
        self.cache.set_user_language(10, "ru")
        self.cache.touch_user({
            "telegram_id": 10, "username": "tester2", "language": None,
            "first_source": "tiktok",
        }, "2026-02-01T00:00:00+00:00")
        profile = self.cache.get_user(10)
        self.assertEqual(profile["language"], "ru")
        self.assertEqual(profile["first_source"], "instagram")
        self.assertEqual(profile["first_seen_at"], first_seen)
        self.assertEqual(self.cache.get_state(10)["current_theme_id"], "theme-1")

    def test_profile_changes_remain_dirty_until_successful_sync(self):
        now = datetime.now(timezone.utc).isoformat()
        self.cache.touch_user({
            "telegram_id": 11, "language": "uz", "first_source": "direct",
        }, now)
        self.assertEqual(len(self.cache.dirty_users()), 1)
        self.cache.mark_users_clean([11])
        self.assertEqual(self.cache.dirty_users(), [])


class SupabaseProfileSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SupabaseDB("https://example.supabase.co", "fake")
        self.db.local.close()
        self.db.local = LocalStateCache(os.path.join(self.tmp.name, "cache.sqlite3"))

    async def asyncTearDown(self):
        self.db.local.close()
        self.tmp.cleanup()

    async def test_repeated_touch_does_not_change_first_source_or_language(self):
        now = datetime.now(timezone.utc).isoformat()
        user = SimpleNamespace(id=15, username="tester", first_name="Test",
                               last_name=None, language_code="uz")
        self.db.local.touch_user({
            "telegram_id": 15, "language": "ru", "first_source": "instagram",
        }, now)
        self.db._request = AsyncMock(return_value=[])
        await self.db.touch(user, first_source="tiktok")
        profile = self.db.local.get_user(15)
        self.assertEqual(profile["first_source"], "instagram")
        self.assertEqual(profile["language"], "ru")

    async def test_traffic_analytics_counts_dynamic_sources_and_languages(self):
        self.db.page_size = 10
        self.db._request = AsyncMock(return_value=[
            {"language": "uz", "first_source": "instagram"},
            {"language": "ru", "first_source": "tiktok"},
            {"language": None, "first_source": None},
            {"language": "uz", "first_source": "new_campaign"},
        ])
        result = await self.db.traffic_analytics()
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["sources"]["unknown"], 1)
        self.assertEqual(result["sources"]["new_campaign"], 1)
        self.assertEqual(result["languages"], {"uz": 2, "ru": 1, "unset": 1})

    async def test_failed_profile_sync_keeps_language_and_source_dirty(self):
        self.db.local.touch_user({
            "telegram_id": 12, "language": "ru", "first_source": "threads",
        }, datetime.now(timezone.utc).isoformat())
        self.db._request = AsyncMock(side_effect=SupabaseError("offline"))
        with self.assertRaises(SupabaseError):
            await self.db.sync_user_state()
        profile = self.db.local.get_user(12)
        self.assertEqual(profile["language"], "ru")
        self.assertEqual(profile["first_source"], "threads")
        self.assertTrue(self.db.local.dirty_users())


if __name__ == "__main__":
    unittest.main()
