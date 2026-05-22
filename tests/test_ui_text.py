import unittest

from app.ui.text import user_home


class UiTextTests(unittest.TestCase):
    def test_user_home_has_fallback_without_destinations(self):
        body = user_home([])
        self.assertIn("Welcome", body)
        self.assertIn("No destination channels", body)


if __name__ == "__main__":
    unittest.main()

