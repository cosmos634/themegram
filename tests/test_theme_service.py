import json
import tempfile
import unittest
from pathlib import Path

from services.theme_service import ThemeDataError, ThemeService


def valid_catalogue():
    return {
        "iOS": {
            "Dark": [{"id": "dark-1", "name": "Night", "url": "https://example.org/night"}],
            "Soft": [], "Anime": [], "Boshqa": [],
        },
        "Android": {
            "Dark": [{"id": "dark-a", "name": "Night A", "url": "https://example.org/night-a"}],
            "Soft": [], "Anime": [], "Boshqa": [],
        },
    }


class ThemeServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "themes.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def write_catalogue(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_load_and_retrieve_by_os_and_category(self):
        self.write_catalogue(valid_catalogue())
        service = ThemeService(self.path)
        service.load()
        self.assertEqual(service.get_random("iOS", "Dark")["id"], "dark-1")
        self.assertEqual(service.get_random("Android", "Dark")["id"], "dark-a")

    def test_empty_category_returns_none(self):
        self.write_catalogue(valid_catalogue())
        service = ThemeService(self.path)
        service.load()
        self.assertIsNone(service.get_random("iOS", "Anime"))

    def test_previous_theme_is_avoided_when_possible(self):
        catalogue = valid_catalogue()
        catalogue["iOS"]["Dark"].append({
            "id": "dark-2", "name": "Night 2", "url": "https://example.org/night-2"
        })
        self.write_catalogue(catalogue)
        service = ThemeService(self.path)
        service.load()
        self.assertEqual(service.get_random("iOS", "Dark", "dark-1")["id"], "dark-2")

    def test_invalid_url_is_rejected(self):
        catalogue = valid_catalogue()
        catalogue["iOS"]["Dark"][0]["url"] = "javascript:alert(1)"
        self.write_catalogue(catalogue)
        with self.assertRaises(ThemeDataError):
            ThemeService(self.path).load()

    def test_malformed_json_is_rejected(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ThemeDataError):
            ThemeService(self.path).load()


if __name__ == "__main__":
    unittest.main()
