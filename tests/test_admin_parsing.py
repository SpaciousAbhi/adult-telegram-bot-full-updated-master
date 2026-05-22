import unittest

from app.routers.admin import normalize_chat_input, parse_duration_seconds


class AdminParsingTests(unittest.TestCase):
    def test_duration_presets_and_words(self):
        self.assertEqual(parse_duration_seconds("1 minute"), 60)
        self.assertEqual(parse_duration_seconds("5 minutes"), 300)
        self.assertEqual(parse_duration_seconds("1 hour"), 3600)
        self.assertEqual(parse_duration_seconds("30m"), 1800)

    def test_public_t_me_link_normalizes_to_username(self):
        self.assertEqual(normalize_chat_input("https://t.me/example_channel/123"), "@example_channel")

    def test_invite_link_is_not_rewritten(self):
        link = "https://t.me/+abcdef"
        self.assertEqual(normalize_chat_input(link), link)

    def test_fix_channel_id(self):
        from app.services.task_runner import fix_channel_id
        self.assertEqual(fix_channel_id(3774139255), -1003774139255)
        self.assertEqual(fix_channel_id("3774139255"), -1003774139255)
        self.assertEqual(fix_channel_id("-3774139255"), -1003774139255)
        self.assertEqual(fix_channel_id("-1003774139255"), -1003774139255)
        self.assertEqual(fix_channel_id("@username"), "@username")
        self.assertEqual(fix_channel_id("not_numeric"), "not_numeric")
        self.assertEqual(fix_channel_id(None), None)


if __name__ == "__main__":
    unittest.main()

