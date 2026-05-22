from __future__ import annotations

from datetime import timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.database import Database
from app.timeutils import utcnow


class ReferralService:
    def __init__(self, db: Database, bot: Bot) -> None:
        self.db = db
        self.bot = bot

    async def settings(self) -> dict[str, Any]:
        runtime = await self.db.get_runtime_settings()
        return runtime.get("referral") or {}

    async def get_or_create_link(self, user_id: int) -> str | None:
        settings = await self.settings()
        channel_id = settings.get("channel_id")
        if not channel_id:
            return None
        existing = await self.db.col("referral_links").find_one({"user_id": int(user_id)})
        if existing and existing.get("invite_link"):
            return existing["invite_link"]
        try:
            invite = await self.bot.create_chat_invite_link(
                chat_id=int(channel_id),
                name=f"ref-{user_id}",
                creates_join_request=False,
            )
            invite_link = invite.invite_link
        except (TelegramBadRequest, TelegramForbiddenError):
            return None
        await self.db.col("referral_links").update_one(
            {"user_id": int(user_id)},
            {
                "$set": {
                    "user_id": int(user_id),
                    "channel_id": int(channel_id),
                    "invite_link": invite_link,
                    "updated_at": utcnow(),
                },
                "$setOnInsert": {"created_at": utcnow()},
            },
            upsert=True,
        )
        return invite_link

    async def record_join(self, invite_link: str | None, joined_user_id: int) -> None:
        if not invite_link:
            return
        link_doc = await self.db.col("referral_links").find_one({"invite_link": invite_link})
        if not link_doc:
            return
        referrer_id = int(link_doc["user_id"])
        if referrer_id == int(joined_user_id):
            return
        try:
            await self.db.col("referral_events").insert_one(
                {
                    "referrer_id": referrer_id,
                    "joined_user_id": int(joined_user_id),
                    "invite_link": invite_link,
                    "created_at": utcnow(),
                }
            )
        except Exception:
            return
        await self.apply_reward_if_earned(referrer_id)

    async def apply_reward_if_earned(self, referrer_id: int) -> None:
        settings = await self.settings()
        required = int(settings.get("required_joins") or 10)
        reward_limit = int(settings.get("reward_limit") or 100)
        reward_days = int(settings.get("reward_days") or 5)
        count = await self.db.col("referral_events").count_documents({"referrer_id": int(referrer_id)})
        if count < required:
            return
        expires_at = utcnow() + timedelta(days=reward_days)
        await self.db.col("users").update_one(
            {"telegram_id": int(referrer_id)},
            {
                "$set": {
                    "referral_reward_until": expires_at,
                    "referral_reward_limit": reward_limit,
                    "referral_reward_join_count": count,
                }
            },
        )

