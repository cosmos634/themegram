import unittest
from types import SimpleNamespace

from handlers.admin import is_admin, is_theme_url


class AdminValidationTests(unittest.TestCase):
    def test_admin_requires_configured_matching_id(self):
        self.assertTrue(is_admin(123, SimpleNamespace(admin_id=123)))
        self.assertFalse(is_admin(456, SimpleNamespace(admin_id=123)))
        self.assertFalse(is_admin(123, SimpleNamespace(admin_id=None)))

    def test_only_telegram_addtheme_https_urls_are_accepted(self):
        self.assertTrue(is_theme_url("https://t.me/addtheme/AbCd123"))
        self.assertFalse(is_theme_url("http://t.me/addtheme/AbCd123"))
        self.assertFalse(is_theme_url("https://example.com/addtheme/AbCd123"))
        self.assertFalse(is_theme_url("https://t.me/other/AbCd123"))
        self.assertFalse(is_theme_url("https://t.me/addtheme/"))


if __name__ == "__main__":
    unittest.main()
