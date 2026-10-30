import unittest

from locales import normalize_language, t


class LocaleTests(unittest.TestCase):
    def test_supported_languages(self):
        self.assertEqual(t("uz", "menu_themes"), "🎨 Temalar")
        self.assertEqual(t("ru", "menu_themes"), "🎨 Темы")

    def test_unknown_language_falls_back_to_uzbek(self):
        self.assertEqual(normalize_language("xx"), "uz")
        self.assertEqual(t("xx", "menu_channel"), "📢 Kanalga a’zo bo‘lish")

if __name__ == "__main__":
    unittest.main()
