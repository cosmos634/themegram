import os
import unittest
from unittest.mock import patch

from config import load_settings


class ConfigTests(unittest.TestCase):
    def test_required_values_are_validated(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing required"):
                load_settings()

    def test_valid_environment(self):
        env = {
            "BOT_TOKEN": "123456:fake-test-token",
            "CHANNEL_URL": "https://t.me/example",
            "WEBHOOK_BASE_URL": "https://themegram.example.com",
            "WEBHOOK_SECRET": "secret_with-valid-characters",
            "PORT": "10000",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()
        self.assertEqual(settings.port, 10000)
        self.assertEqual(settings.webhook_path, "/telegram/webhook")
        self.assertEqual(settings.channel_url, "https://t.me/example")

    def test_invalid_webhook_secret_is_rejected(self):
        env = {
            "BOT_TOKEN": "test-token",
            "CHANNEL_URL": "https://t.me/example",
            "WEBHOOK_BASE_URL": "https://themegram.example.com",
            "WEBHOOK_SECRET": "contains spaces",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "WEBHOOK_SECRET"):
                load_settings()


if __name__ == "__main__":
    unittest.main()
