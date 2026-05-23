from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.database import Database
from app.timeutils import utcnow


JOINED_STATUSES = {"creator", "administrator", "member"}
REQUEST_DONE_STATUSES = {"pending", "approved"}


def member_status_value(member: Any) -> str:
    raw = getattr(member, "status", None)
    return getattr(raw, "value", raw) or ""


class ForceSubscriptionService:
    def __init__(self, db: Database, bot: Bot) -> None:
        self.db = db
        self.bot = bot

    async def targets(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"enabled": True} if enabled_only else {}
        cursor = self.db.col("force_targets").find(query).sort("created_at", 1)
        return [doc async for doc in cursor]

    async def add_target(
        self,
        chat_id: int,
        title: str | None = None,
        mode: str = "join",
        invite_link: str | None = None,
    ) -> dict[str, Any]:
        mode = "request" if mode == "request" else "join"
        link = invite_link or await self.create_invite_link(chat_id, mode)
        doc = {
            "chat_id": int(chat_id),
            "title": title or str(chat_id),
            "mode": mode,
            "enabled": True,
            "invite_link": link,
            "updated_at": utcnow(),
        }
        await self.db.col("force_targets").update_one(
            {"chat_id": int(chat_id)},
            {"$set": doc, "$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )
        return await self.db.col("force_targets").find_one({"chat_id": int(chat_id)}) or doc

    async def create_invite_link(self, chat_id: int, mode: str) -> str | None:
        try:
            invite = await self.bot.create_chat_invite_link(
                chat_id=chat_id,
                name=f"force-{mode}",
                creates_join_request=(mode == "request"),
            )
            return invite.invite_link
        except (TelegramBadRequest, TelegramForbiddenError):
            return None

    async def refresh_invite_link(self, chat_id: int) -> str | None:
        target = await self.db.col("force_targets").find_one({"chat_id": int(chat_id)})
        if not target:
            return None
        link = await self.create_invite_link(int(chat_id), target.get("mode", "join"))
        await self.db.col("force_targets").update_one(
            {"chat_id": int(chat_id)}, {"$set": {"invite_link": link, "updated_at": utcnow()}}
        )
        return link

    async def toggle_enabled(self, chat_id: int) -> None:
        target = await self.db.col("force_targets").find_one({"chat_id": int(chat_id)})
        if not target:
            return
        await self.db.col("force_targets").update_one(
            {"chat_id": int(chat_id)},
            {"$set": {"enabled": not bool(target.get("enabled", True)), "updated_at": utcnow()}},
        )

    async def set_mode(self, chat_id: int, mode: str) -> None:
        mode = "request" if mode == "request" else "join"
        link = await self.create_invite_link(int(chat_id), mode)
        await self.db.col("force_targets").update_one(
            {"chat_id": int(chat_id)},
            {"$set": {"mode": mode, "invite_link": link, "updated_at": utcnow()}},
        )

    async def remove_target(self, chat_id: int) -> None:
        await self.db.col("force_targets").delete_one({"chat_id": int(chat_id)})

    async def missing_targets(self, user_id: int) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for target in await self.targets(enabled_only=True):
            chat_id = int(target["chat_id"])
            if await self.is_joined(chat_id, user_id):
                continue
            if target.get("mode") == "request" and await self.has_request(chat_id, user_id):
                continue
            missing.append(target)
        return missing

    async def missing_destinations(self, user_id: int, destinations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for dest in destinations:
            chat_id = dest.get("chat_id")
            if not chat_id:
                continue
            try:
                if await self.is_joined(int(chat_id), user_id):
                    continue
            except Exception:
                pass
            missing.append(dest)
        return missing

    async def is_joined(self, chat_id: int, user_id: int) -> bool:
        try:
            member = await self.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        except (TelegramBadRequest, TelegramForbiddenError):
            return False
        return member_status_value(member) in JOINED_STATUSES

    async def has_request(self, chat_id: int, user_id: int) -> bool:
        doc = await self.db.col("force_requests").find_one({"chat_id": int(chat_id), "user_id": int(user_id)})
        return bool(doc and doc.get("status") in REQUEST_DONE_STATUSES)

    async def record_join_request(self, chat_id: int, user_id: int, invite_link: str | None = None) -> None:
        await self.db.col("force_requests").update_one(
            {"chat_id": int(chat_id), "user_id": int(user_id)},
            {
                "$set": {
                    "chat_id": int(chat_id),
                    "user_id": int(user_id),
                    "invite_link": invite_link,
                    "status": "pending",
                    "updated_at": utcnow(),
                },
                "$setOnInsert": {"created_at": utcnow()},
            },
            upsert=True,
        )

