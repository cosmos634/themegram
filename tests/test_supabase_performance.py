import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from database.supabase import SupabaseDB, SupabaseError

class CacheTests(unittest.IsolatedAsyncioTestCase):
    def db(self, ttl=60): return SupabaseDB("https://example.supabase.co","fake",theme_cache_ttl=ttl,page_size=2)

    async def test_cache_hit_and_expiry(self):
        db=self.db(); db._load_active_themes=AsyncMock(side_effect=[[{"id":"a"}],[{"id":"b"}]])
        self.assertEqual((await db.get_random("iOS","Dark"))["id"],"a")
        await db.get_random("iOS","Dark"); db._load_active_themes.assert_awaited_once()
        db._theme_cache[("iOS","Dark")]=(0,[{"id":"stale"}])
        self.assertEqual((await db.get_random("iOS","Dark"))["id"],"b")
        self.assertEqual(db._load_active_themes.await_count,2)

    async def test_previous_theme_excluded(self):
        db=self.db(); db._load_active_themes=AsyncMock(return_value=[{"id":"a"},{"id":"b"}])
        with patch("database.supabase.random.choice",side_effect=lambda rows: rows[0]) as choice:
            self.assertEqual((await db.get_random("iOS","Dark","a"))["id"],"b")
        self.assertEqual(choice.call_args.args[0],[{"id":"b"}])

    async def test_empty_dataset_cached(self):
        db=self.db(); db._load_active_themes=AsyncMock(return_value=[])
        self.assertIsNone(await db.get_random("Android","Anime"))
        self.assertIsNone(await db.get_random("Android","Anime")); db._load_active_themes.assert_awaited_once()

    async def test_stale_fallback_on_refresh_failure(self):
        db=self.db(); db._theme_cache[("iOS","Soft")]=(0,[{"id":"cached"}])
        db._load_active_themes=AsyncMock(side_effect=SupabaseError("offline"))
        self.assertEqual((await db.get_random("iOS","Soft"))["id"],"cached")

    async def test_refresh_failure_without_cache_raises(self):
        db=self.db(); db._load_active_themes=AsyncMock(side_effect=SupabaseError("offline"))
        with self.assertRaises(SupabaseError): await db.get_random("iOS","Soft")

    async def test_concurrent_misses_share_refresh(self):
        db=self.db(); gate=asyncio.Event()
        async def loader(*args): await gate.wait(); return [{"id":"cached"}]
        db._load_active_themes=AsyncMock(side_effect=loader)
        tasks=[asyncio.create_task(db.get_random("iOS","Dark")) for _ in range(5)]
        await asyncio.sleep(0); gate.set(); await asyncio.gather(*tasks)
        db._load_active_themes.assert_awaited_once()

    async def test_state_upsert_preserves_unmodified_fields(self):
        db=self.db(); db._request=AsyncMock(return_value=[])
        await db.set_theme(42,"theme-1"); call=db._request.await_args
        self.assertEqual(call.args[:2],("POST","user_states"))
        self.assertEqual(call.kwargs["params"],{"on_conflict":"telegram_id"})
        self.assertNotIn("selected_os",call.kwargs["json"])

    async def test_get_state_does_not_write_on_read(self):
        db=self.db(); db._request=AsyncMock(return_value=[{"telegram_id":1,"last_activity":datetime.now(timezone.utc).isoformat(),"selected_os":"iOS"}])
        self.assertEqual((await db.get_state(1))["selected_os"],"iOS")
        self.assertEqual(db._request.await_count,1)

    async def test_admin_add_invalidates_cache(self):
        db=self.db(); db._theme_cache[("iOS","Dark")]=(9999999999,[{"id":"old"}])
        db._request=AsyncMock(return_value=[{"id":"new"}])
        await db.add_theme({"id":"new"}); self.assertEqual(db._theme_cache,{})

if __name__ == "__main__": unittest.main()
