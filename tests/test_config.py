import os
import unittest
from unittest.mock import patch

from app.config import ConfigError, load_settings


class ConfigTests(unittest.TestCase):
    def test_loads_minimum_mongo_config(self):
        env = {
            "BOT_TOKEN": "123:test",
            "ADMIN_ID": "111,222",
            "MONGO_URI": "mongodb://localhost:27017/test",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()
        self.assertEqual(settings.primary_admin_id, 111)
        self.assertEqual(settings.database_name, "adult_telegram_bot")

    def test_database_url_must_not_be_postgres(self):
        env = {
            "BOT_TOKEN": "123:test",
            "ADMIN_ID": "111",
            "DATABASE_URL": "postgres://user:pass@example.com/db",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError):
                load_settings()


if __name__ == "__main__":
    unittest.main()

