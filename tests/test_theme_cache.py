import unittest
from unittest.mock import AsyncMock

from database.supabase import SupabaseDB


class ThemeCacheTests(unittest.IsolatedAsyncioTestCase):
    def make_db(self, ttl=60):
        db = SupabaseDB("https://example.supabase.co", "not-a-real-key", cache_ttl_seconds=ttl)
        db._request = AsyncMock()
        return db

    async def test_cache_hit_avoids_second_request(self):
        db = self.make_db()
        db._request.return_value = [{"id": "1", "name": "Theme"}]
        first = await db.get_random("iOS", "Dark")
        second = await db.get_random("iOS", "Dark")
        self.assertEqual(first["id"], "1")
        self.assertEqual(second["id"], "1")
        db._request.assert_awaited_once()

    async def test_random_selection_excludes_previous_when_possible(self):
        db = self.make_db()
        db._request.return_value = [{"id": "1"}, {"id": "2"}]
        for _ in range(20):
            result = await db.get_random("iOS", "Dark", previous_id="1")
            self.assertEqual(result["id"], "2")

    async def test_empty_cache_returns_none(self):
        db = self.make_db()
        db._request.return_value = []
        self.assertIsNone(await db.get_random("Android", "Anime"))

    async def test_failed_initial_refresh_raises(self):
        from database.supabase import SupabaseError
        db = self.make_db()
        db._request.side_effect = SupabaseError("temporary failure")
        with self.assertRaises(SupabaseError):
            await db.get_random("iOS", "Soft")

    async def test_expired_cache_refreshes(self):
        db = self.make_db(ttl=0)
        db._request.side_effect = [
            [{"id": "1"}],
            [{"id": "2"}],
        ]
        self.assertEqual((await db.get_random("iOS", "Dark"))["id"], "1")
        self.assertEqual((await db.get_random("iOS", "Dark"))["id"], "2")
        self.assertEqual(db._request.await_count, 2)

    async def test_admin_theme_write_invalidates_cache(self):
        db = self.make_db()
        db._theme_cache[("iOS", "Dark")] = (9999999999, [{"id": "old"}])
        db._request.return_value = [{"id": "new", "name": "New"}]
        await db.add_theme({"id": "new", "platform": "iOS", "category": "Dark"})
        self.assertNotIn(("iOS", "Dark"), db._theme_cache)

    async def test_state_update_uses_one_upsert_and_preserves_omitted_fields(self):
        db = self.make_db()
        await db.set_theme(123, "theme-1")
        db._request.assert_awaited_once()
        args = db._request.await_args
        self.assertEqual(args.args, ("POST", "user_states"))
        self.assertEqual(args.kwargs["json"]["current_theme_id"], "theme-1")
        self.assertNotIn("selected_os", args.kwargs["json"])
        self.assertIn("resolution=merge-duplicates", args.kwargs["prefer"])


if __name__ == "__main__":
    unittest.main()
