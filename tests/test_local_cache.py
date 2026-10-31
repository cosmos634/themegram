import json
import tempfile
import unittest
from pathlib import Path

from database.local_cache import LocalStateCache


class LocalCacheSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = LocalStateCache(str(Path(self.temp_dir.name) / "cache.sqlite3"))

    def tearDown(self):
        self.cache.close()
        self.temp_dir.cleanup()

    def test_user_snapshot_cleaning_preserves_first_seen_column(self):
        self.cache.touch_user({
            "telegram_id": 101,
            "username": "tester",
            "language": None,
            "first_source": "instagram",
        }, "2026-10-31T10:00:00+00:00")

        stored = self.cache.conn.execute(
            "SELECT profile_json, first_seen_at, dirty FROM cached_users WHERE telegram_id=101"
        ).fetchone()
        self.assertNotIn("first_seen_at", json.loads(stored["profile_json"]))
        self.assertEqual(stored["dirty"], 1)

        snapshot = self.cache.dirty_users()
        self.cache.mark_users_clean(snapshot)
        stored = self.cache.conn.execute(
            "SELECT dirty FROM cached_users WHERE telegram_id=101"
        ).fetchone()
        self.assertEqual(stored["dirty"], 0)

    def test_new_user_edit_during_sync_stays_dirty(self):
        now = "2026-10-31T10:00:00+00:00"
        self.cache.touch_user({
            "telegram_id": 102,
            "username": "before",
            "language": None,
            "first_source": "tiktok",
        }, now)
        uploaded_snapshot = self.cache.dirty_users()

        self.cache.touch_user({
            "telegram_id": 102,
            "username": "after",
            "language": "ru",
            "first_source": "direct",
        }, "2026-10-31T10:01:00+00:00")
        self.cache.mark_users_clean(uploaded_snapshot)

        row = self.cache.conn.execute(
            "SELECT profile_json, dirty FROM cached_users WHERE telegram_id=102"
        ).fetchone()
        self.assertEqual(row["dirty"], 1)
        profile = json.loads(row["profile_json"])
        self.assertEqual(profile["username"], "after")
        self.assertEqual(profile["first_source"], "tiktok")
        self.assertEqual(profile["language"], "ru")

    def test_state_edit_during_sync_stays_dirty(self):
        self.cache.update_state(103, {"selected_os": "iOS"}, "2026-10-31T10:00:00+00:00")
        uploaded_snapshot = self.cache.dirty_states()

        self.cache.update_state(103, {"selected_category": "Dark"}, "2026-10-31T10:01:00+00:00")
        self.cache.mark_states_clean(uploaded_snapshot)

        row = self.cache.conn.execute(
            "SELECT state_json, dirty FROM cached_states WHERE telegram_id=103"
        ).fetchone()
        self.assertEqual(row["dirty"], 1)
        state = json.loads(row["state_json"])
        self.assertEqual(state["selected_os"], "iOS")
        self.assertEqual(state["selected_category"], "Dark")


if __name__ == "__main__":
    unittest.main()
