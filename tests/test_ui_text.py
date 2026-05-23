import unittest

from app.ui.text import user_home, task_detail


class UiTextTests(unittest.TestCase):
    def test_user_home_has_fallback_without_destinations(self):
        body = user_home([])
        self.assertIn("Welcome", body)
        self.assertIn("No destination channels", body)

    def test_task_detail_renders_pending_and_last_posted(self):
        task = {
            "name": "Test Task",
            "status": "active",
            "sources": [{"value": "src"}],
            "destinations": [{"chat_id": 123}],
            "storage_channel": -100456,
            "interval_seconds": 60,
            "posts_per_interval": 2,
            "last_run_at": None,
            "next_run_at": None,
            "next_collect_at": None,
            "last_saved_count": 5,
            "last_post_count": 1,
            "last_error": "Some Telegram error",
        }
        body = task_detail(task, pending_count=42, last_posted_token="abcde123")
        self.assertIn("Task: Test Task", body)
        self.assertIn("Pending Videos (in storage): <code>42</code>", body)
        self.assertIn("Last posted token: <code>abcde123</code>", body)
        self.assertIn("Last result: <code>Some Telegram error</code>", body)


if __name__ == "__main__":
    unittest.main()

