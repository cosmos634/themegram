import unittest

from services.traffic import parse_start_source


class TrafficSourceTests(unittest.TestCase):
    def test_known_sources_and_dynamic_source(self):
        self.assertEqual(parse_start_source("instagram"), "instagram")
        self.assertEqual(parse_start_source("TikTok"), "tiktok")
        self.assertEqual(parse_start_source("facebook"), "facebook")

    def test_plain_start_is_direct(self):
        self.assertEqual(parse_start_source(None), "direct")
        self.assertEqual(parse_start_source(""), "direct")

    def test_invalid_payload_is_unknown(self):
        self.assertEqual(parse_start_source("bad source"), "unknown")
        self.assertEqual(parse_start_source("a" * 65), "unknown")
        self.assertEqual(parse_start_source("x/y"), "unknown")

if __name__ == "__main__":
    unittest.main()
