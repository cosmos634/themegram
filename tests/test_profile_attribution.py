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
        self.cache.set_user_language(10, "ru")
        self.cache.touch_user({
            "telegram_id": 10, "username": "tester2", "language": None,
            "first_source": "tiktok",
        }, "2026-02-01T00:00:00+00:00")
        profile = self.cache.get_user(10)
        self.assertEqual(profile["language"], "ru")
        self.assertEqual(profile["first_source"], "instagram")
        self.assertEqual(profile["first_seen_at"], first_seen)

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
