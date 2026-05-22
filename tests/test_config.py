import os
import unittest
from unittest.mock import patch

from app.config import ConfigError, load_settings


class ConfigTests(unittest.TestCase):
    def test_loads_minimum_mongo_config(self):
        env = {
            "BOT_TOKEN": "123:test",
            "ADMIN_IDS": "111,222",
            "OWNER_IDS": "333,444",
            "MONGO_URI": "mongodb://localhost:27017/test",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()
        self.assertEqual(settings.primary_owner_id, 333)
        self.assertIn(444, settings.manager_ids)
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

    def test_postgres_database_url_becomes_legacy_when_mongo_exists(self):
        env = {
            "BOT_TOKEN": "123:test",
            "ADMIN_ID": "111",
            "MONGO_URI": "mongodb://localhost:27017/test",
            "DATABASE_URL": "postgres://user:pass@example.com/db",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()
        self.assertEqual(settings.legacy_database_url, "postgres://user:pass@example.com/db")


if __name__ == "__main__":
    unittest.main()
