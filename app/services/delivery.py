from __future__ import annotations

from datetime import timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import Settings
from app.database import Database
from app.services.access import decide_access, today_query
from app.services.referrals import ReferralService
from app.timeutils import utcnow


class DeliveryService:
    def __init__(self, db: Database, bot: Bot, settings: Settings | None = None) -> None:
        self.db = db
        self.bot = bot
        self.settings = settings

    async def deliver(self, token: str, user_id: int, chat_id: int) -> bool:
        media = await self.db.col("media").find_one({"token": token})
        if not media:
            await self.bot.send_message(chat_id, "This video link is no longer available.")
            return False

        runtime = await self.db.get_runtime_settings()
        user = await self.db.get_user(user_id)
        downloads_today = await self.db.col("downloads").count_documents({"user_id": int(user_id), **today_query()})
        decision = decide_access(user, runtime, downloads_today)
        if not decision.allowed:
            await self.send_limit_exhausted(chat_id, user_id, runtime, decision.limit)
            return False

        storage_chat_id = media.get("storage_chat_id")
        storage_message_id = media.get("storage_message_id")
        if not storage_chat_id or not storage_message_id:
            await self.bot.send_message(chat_id, "Video storage is not ready for this item.")
            return False

        try:
            if runtime.get("forward_tag_enabled"):
                sent = await self.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=int(storage_chat_id),
                    message_id=int(storage_message_id),
                )
            else:
                sent = await self.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=int(storage_chat_id),
                    message_id=int(storage_message_id),
                )
        except (TelegramBadRequest, TelegramForbiddenError):
            await self.bot.send_message(chat_id, "I could not deliver this video. Please try again later.")
            return False

        await self.db.col("downloads").insert_one(
            {
                "user_id": int(user_id),
                "media_id": media["_id"],
                "token": token,
                "downloaded_at": utcnow(),
            }
        )
        await self.schedule_delivery_delete(runtime, chat_id, sent.message_id)
        return True

    async def send_limit_exhausted(self, chat_id: int, user_id: int, runtime: dict[str, Any], limit: int) -> None:
        access = runtime.get("access") or {}
        message = access.get("limit_message") or "Your free limit is exhausted. Come back tomorrow or take premium."
        methods = ", ".join(access.get("premium_methods") or ["UPI", "Crypto", "Binance"])
        referral_link = await ReferralService(self.db, self.bot).get_or_create_link(user_id)
        referral = runtime.get("referral") or {}
        referral_text = ""
        if referral_link:
            referral_text = (
                "\n\nReferral option: "
                f"if {referral.get('required_joins', 10)} users join through your link, "
                f"your daily limit becomes {referral.get('reward_limit', 100)} videos for "
                f"{referral.get('reward_days', 5)} days."
            )
        admin_id = self.settings.primary_admin_id if self.settings else chat_id
        rows = [[InlineKeyboardButton(text="Contact Admin to Buy Premium", url=f"tg://user?id={admin_id}")]]
        if referral_link:
            rows.append([InlineKeyboardButton(text="Referral to Earn Premium", url=referral_link)])
        await self.bot.send_message(
            chat_id,
            f"{message}\n\nDaily free limit: {limit}\nPayment methods: {methods}{referral_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    async def schedule_delivery_delete(self, runtime: dict[str, Any], chat_id: int, message_id: int) -> None:
        settings = runtime.get("auto_delete") or {}
        if not settings.get("delivery_enabled"):
            return
        seconds = int(settings.get("delivery_seconds") or 0)
        if seconds <= 0:
            return
        await self.db.col("messages_to_delete").insert_one(
            {
                "chat_id": int(chat_id),
                "message_id": int(message_id),
                "kind": "delivery",
                "due_at": utcnow() + timedelta(seconds=seconds),
                "done": False,
                "created_at": utcnow(),
            }
        )
