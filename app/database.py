from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import ServerSelectionTimeoutError

from app.config import Settings
from app.timeutils import utcnow


class MongoStartupError(RuntimeError):
    """Raised when MongoDB cannot be reached during startup."""


DEFAULT_ACCESS_SETTINGS: dict[str, Any] = {
    "free_daily_limit": 5,
    "limit_message": (
        "Your free limit is exhausted. Come back tomorrow, buy premium, "
        "or use referrals to increase your daily limit."
    ),
    "premium_methods": ["UPI", "Crypto", "Binance"],
}

DEFAULT_REFERRAL_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "channel_id": None,
    "required_joins": 10,
    "reward_limit": 100,
    "reward_days": 5,
}

DEFAULT_AUTO_DELETE_SETTINGS: dict[str, Any] = {
    "destination_enabled": False,
    "destination_seconds": 0,
    "delivery_enabled": False,
    "delivery_seconds": 0,
}

DEFAULT_RUNTIME_SETTINGS: dict[str, Any] = {
    "forward_tag_enabled": False,
    "access": DEFAULT_ACCESS_SETTINGS,
    "referral": DEFAULT_REFERRAL_SETTINGS,
    "auto_delete": DEFAULT_AUTO_DELETE_SETTINGS,
    "destination_channels": [],
}


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        self.client = AsyncIOMotorClient(
            self.settings.database_url,
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
            uuidRepresentation="standard",
        )
        self.db = self.client[self.settings.database_name]
        try:
            await self.client.admin.command("ping")
        except ServerSelectionTimeoutError as exc:
            raise MongoStartupError(
                "MongoDB is unreachable. Check MONGO_URI, username/password, TLS, and Atlas Network Access."
            ) from exc
        await self.ensure_indexes()
        await self.ensure_defaults()

    def close(self) -> None:
        if self.client:
            self.client.close()

    def col(self, name: str):
        if self.db is None:
            raise RuntimeError("Database is not connected")
        return self.db[name]

    async def ensure_indexes(self) -> None:
        await self.col("users").create_index("telegram_id", unique=True, sparse=True)
        await self.col("users").create_index([("last_seen_at", DESCENDING)])
        await self.col("tasks").create_index([("status", ASCENDING), ("next_run_at", ASCENDING)])
        await self.col("tasks").create_index("name")
        await self.col("media").create_index("token", unique=True)
        await self.col("media").create_index("fingerprint", unique=True)
        await self.col("media").create_index([("task_id", ASCENDING), ("destination_status", ASCENDING), ("created_at", ASCENDING)])
        await self.col("media").create_index([("task_id", ASCENDING), ("storage_status", ASCENDING), ("created_at", ASCENDING)])
        await self.col("force_targets").create_index("chat_id", unique=True)
        await self.col("force_targets").create_index([("enabled", ASCENDING), ("mode", ASCENDING)])
        await self.col("force_requests").create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        await self.col("admin_states").create_index("admin_id", unique=True)
        await self.col("downloads").create_index([("user_id", ASCENDING), ("downloaded_at", DESCENDING)])
        await self.col("broadcasts").create_index([("created_at", DESCENDING)])
        await self.col("destination_posts").create_index([("media_token", ASCENDING), ("chat_id", ASCENDING)], unique=True)
        await self.col("messages_to_delete").create_index([("due_at", ASCENDING), ("done", ASCENDING)])
        await self.col("referral_links").create_index("user_id", unique=True)
        await self.col("referral_links").create_index("invite_link", unique=True, sparse=True)
        await self.col("referral_events").create_index(
            [("referrer_id", ASCENDING), ("joined_user_id", ASCENDING)], unique=True
        )
        await self.col("settings").create_index("key", unique=True)

    async def ensure_defaults(self) -> None:
        await self.col("settings").update_one(
            {"key": "runtime"},
            {"$setOnInsert": {"key": "runtime", "value": DEFAULT_RUNTIME_SETTINGS, "updated_at": utcnow()}},
            upsert=True,
        )
        await self.col("userbot").update_one(
            {"_id": "default"},
            {"$setOnInsert": {"_id": "default", "session_string": None, "phone": None, "updated_at": utcnow()}},
            upsert=True,
        )

    async def get_runtime_settings(self) -> dict[str, Any]:
        doc = await self.col("settings").find_one({"key": "runtime"}) or {}
        value = dict(DEFAULT_RUNTIME_SETTINGS)
        stored = doc.get("value") or {}
        for key, default_value in DEFAULT_RUNTIME_SETTINGS.items():
            if isinstance(default_value, dict):
                merged = dict(default_value)
                merged.update(stored.get(key) or {})
                value[key] = merged
            else:
                value[key] = stored.get(key, default_value)
        return value

    async def set_runtime_path(self, path: str, value: Any) -> None:
        await self.col("settings").update_one(
            {"key": "runtime"},
            {"$set": {f"value.{path}": value, "updated_at": utcnow()}},
            upsert=True,
        )

    async def upsert_user(self, telegram_user: Any, referred_by: int | None = None) -> dict[str, Any]:
        now = utcnow()
        telegram_id = int(telegram_user.id)
        existing = await self.col("users").find_one(
            {"$or": [{"telegram_id": telegram_id}, {"user_id": telegram_id}, {"id": telegram_id}]}
        )
        selector = {"_id": existing["_id"]} if existing else {"telegram_id": telegram_id}
        update: dict[str, Any] = {
            "$set": {
                "telegram_id": telegram_id,
                "username": getattr(telegram_user, "username", None),
                "first_name": getattr(telegram_user, "first_name", None),
                "last_name": getattr(telegram_user, "last_name", None),
                "last_seen_at": now,
            },
            "$setOnInsert": {
                "first_seen_at": now,
                "plan": "free",
                "premium_until": None,
                "referral_reward_until": None,
                "referral_reward_limit": None,
                "referred_by": referred_by,
            },
        }
        await self.col("users").update_one(selector, update, upsert=True)
        return await self.col("users").find_one({"telegram_id": telegram_id}) or {}

    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        telegram_id = int(telegram_id)
        return await self.col("users").find_one(
            {"$or": [{"telegram_id": telegram_id}, {"user_id": telegram_id}, {"id": telegram_id}]}
        )

    async def set_pending_action(self, telegram_id: int, action: dict[str, Any] | None) -> None:
        if action is None:
            await self.col("users").update_one({"telegram_id": int(telegram_id)}, {"$unset": {"pending_action": ""}})
            return
        await self.col("users").update_one(
            {"telegram_id": int(telegram_id)},
            {"$set": {"pending_action": action, "pending_action_at": utcnow()}},
            upsert=True,
        )
