import unittest
from unittest.mock import AsyncMock

from services.theme_service import ThemeService


class ThemeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_queries_supabase_with_platform_and_category(self):
        db = AsyncMock()
        db.get_random.return_value = {"id": "x", "name": "Night"}
        service = ThemeService(db)
        result = await service.get_random("iOS", "Dark")
        self.assertEqual(result["id"], "x")
        db.get_random.assert_awaited_once_with("iOS", "Dark", None)

    async def test_previous_theme_is_passed_to_repository(self):
        db = AsyncMock()
        db.get_random.return_value = {"id": "next"}
        result = await ThemeService(db).get_random("Android", "Anime", "previous")
        self.assertEqual(result["id"], "next")
        db.get_random.assert_awaited_once_with("Android", "Anime", "previous")

    async def test_invalid_platform_or_category_rejected(self):
        service = ThemeService(AsyncMock())
        with self.assertRaises(ValueError):
            await service.get_random("Windows", "Dark")
        with self.assertRaises(ValueError):
            await service.get_random("iOS", "Unknown")


if __name__ == "__main__":
    unittest.main()
