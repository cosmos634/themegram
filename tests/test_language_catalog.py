import unittest
from unittest.mock import AsyncMock

from database.supabase import SupabaseDB
from handlers.admin_languages import valid_language_url


class LanguageCatalogTests(unittest.IsolatedAsyncioTestCase):
    def test_only_telegram_setlanguage_links_are_accepted(self):
        self.assertTrue(valid_language_url("https://t.me/setlanguage/uz"))
        self.assertTrue(valid_language_url("https://www.t.me/setlanguage/en"))
        self.assertFalse(valid_language_url("http://t.me/setlanguage/uz"))
        self.assertFalse(valid_language_url("https://example.com/setlanguage/uz"))
        self.assertFalse(valid_language_url("https://t.me/addtheme/theme"))

    async def test_admin_events_are_not_recorded(self):
        db = SupabaseDB("https://example.supabase.co", "fake", ignored_user_ids={77})
        db._request = AsyncMock()
        await db.track_event(77, "bot_started")
        db._request.assert_not_awaited()
        db.local.close()

    async def test_event_analytics_excludes_admin_id(self):
        db = SupabaseDB("https://example.supabase.co", "fake", ignored_user_ids={77})
        db._request = AsyncMock(return_value=[])
        await db.event_analytics(30)
        params = db._request.await_args.kwargs["params"]
        self.assertEqual(params["telegram_id"], "not.in.(77)")
        db.local.close()

    async def test_broadcast_targets_only_selected_language_and_excludes_admin(self):
        db = SupabaseDB("https://example.supabase.co", "fake", ignored_user_ids={77})
        db._request = AsyncMock(return_value=[])
        await db.user_ids(language="ru")
        params = db._request.await_args.kwargs["params"]
        self.assertEqual(params["language"], "eq.ru")
        self.assertEqual(params["telegram_id"], "not.in.(77)")
        db.local.close()


if __name__ == "__main__":
    unittest.main()
