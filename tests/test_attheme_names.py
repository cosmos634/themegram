import unittest

from handlers.attheme import normalize_theme_name


class ThemeNameTests(unittest.TestCase):
    def test_normalizes_spaces_and_extension(self):
        self.assertEqual(normalize_theme_name("My Cool Theme.attheme"), "My_Cool_Theme")

    def test_keeps_unicode_letters(self):
        self.assertEqual(normalize_theme_name("Тунги осмон"), "Тунги_осмон")

    def test_rejects_empty_and_punctuation_only(self):
        for value in ("", "   ", "!!!", ".attheme"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_theme_name(value)

    def test_limits_filename_length(self):
        self.assertEqual(len(normalize_theme_name("A" * 100)), 48)


if __name__ == "__main__":
    unittest.main()
