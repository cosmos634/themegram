import unittest

from locales import t


class EngagingCopyTests(unittest.TestCase):
    def test_welcome_explains_the_image_to_theme_feature(self):
        for language, expected in (("uz", "Rasmdan tema yaratish"), ("ru", "Создать тему из изображения")):
            message = t(language, "welcome")
            self.assertIn(expected, message)
            self.assertIn("iOS", message)
            self.assertIn("Android", message)

    def test_image_creation_guidance_is_actionable_in_both_languages(self):
        for language in ("uz", "ru"):
            intro = t(language, "attheme_intro")
            self.assertIn("JPG" if language == "uz" else "JPG", intro)
            self.assertIn("10 MB" if language == "uz" else "10 МБ", intro)
            self.assertIn("/cancel", intro)
            self.assertIn(".attheme", intro)

    def test_success_and_error_messages_are_present(self):
        for language in ("uz", "ru"):
            self.assertIn("{theme_name}", t(language, "attheme_ready", theme_name="ThemeGram_Test"))
            for key in ("attheme_processing", "attheme_file_ready", "attheme_image_invalid",
                        "attheme_image_too_large", "attheme_api_error", "favorites_empty",
                        "favorite_saved", "os_prompt", "install_hint"):
                self.assertTrue(t(language, key), f"Missing {key} for {language}")

    def test_russian_and_uzbek_welcome_messages_are_localized(self):
        self.assertIn("xush kelibsiz", t("uz", "welcome").lower())
        self.assertIn("добро пожаловать", t("ru", "welcome").lower())


if __name__ == "__main__":
    unittest.main()
