import unittest

from app.callbacks import cb, split_cb


class CallbackTests(unittest.TestCase):
    def test_callback_round_trip(self):
        value = cb("task", "open", "abc123")
        self.assertEqual(value, "task:open:abc123")
        self.assertEqual(split_cb(value), ["task", "open", "abc123"])

    def test_callback_length_guard(self):
        with self.assertRaises(ValueError):
            cb("x" * 65)


if __name__ == "__main__":
    unittest.main()

