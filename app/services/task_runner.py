from __future__ import annotations

import asyncio
import secrets
from datetime import timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from pymongo.errors import DuplicateKeyError

from app.config import Settings
from app.database import Database
from app.services.userbot import (
    UserbotService,
    download_thumbnail_bytes,
    message_fingerprint,
    message_has_video,
    message_video_info,
)
from app.timeutils import human_seconds, utcnow


ACTIVE_TASK = "active"


class TaskScheduler:
    def __init__(self, db: Database, settings: Settings, bot: Bot) -> None:
        self.db = db
        self.settings = settings
        self.bot = bot
        self._tasks: list[asyncio.Task[Any]] = []
        self._bot_username: str | None = None

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._posting_loop(), name="posting-loop"),
            asyncio.create_task(self._delete_loop(), name="delete-loop"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def bot_username(self) -> str:
        if not self._bot_username:
            me = await self.bot.get_me()
            self._bot_username = me.username or ""
        return self._bot_username

    async def _posting_loop(self) -> None:
        while True:
            await self.run_due_tasks()
            await asyncio.sleep(self.settings.poll_interval_seconds)

    async def run_due_tasks(self) -> None:
        now = utcnow()
        query = {
            "status": ACTIVE_TASK,
            "$or": [{"next_run_at": {"$lte": now}}, {"next_run_at": {"$exists": False}}],
        }
        cursor = self.db.col("tasks").find(query).sort("next_run_at", 1).limit(10)
        async for task in cursor:
            try:
                await self.run_task(task)
            except Exception as exc:
                await self.db.col("tasks").update_one(
                    {"_id": task["_id"]},
                    {
                        "$set": {
                            "last_error": str(exc),
                            "last_run_at": utcnow(),
                            "next_run_at": utcnow() + timedelta(seconds=int(task.get("interval_seconds") or 300)),
                        }
                    },
                )

    async def run_task(self, task: dict[str, Any]) -> None:
        interval = int(task.get("interval_seconds") or 300)
        posts_per_interval = int(task.get("posts_per_interval") or 1)
        runtime = await self.db.get_runtime_settings()

        storage_channel = task.get("storage_channel")
        destinations = [d for d in task.get("destinations", []) if d.get("status", "active") == "active"]
        sources = [s for s in task.get("sources", []) if s.get("status", "active") == "active"]
        if not storage_channel or not destinations or not sources:
            await self._finish_task_run(task, interval, "Task needs active sources, destinations, and storage channel")
            return

        userbot = UserbotService(self.db, self.settings)
        client = await userbot.client()
        if not client:
            await self._finish_task_run(task, interval, "Userbot is not logged in or not configured")
            return

        posted = 0
        updated_sources = list(task.get("sources", []))
        for source in updated_sources:
            if posted >= posts_per_interval:
                break
            if source.get("status", "active") != "active":
                continue
            count = await self._collect_from_source(
                client=client,
                task=task,
                source=source,
                storage_channel=storage_channel,
                destinations=destinations,
                runtime=runtime,
                remaining=posts_per_interval - posted,
            )
            posted += count

        await self.db.col("tasks").update_one(
            {"_id": task["_id"]},
            {
                "$set": {
                    "sources": updated_sources,
                    "last_error": None if posted else "No new non-duplicate videos found",
                    "last_post_count": posted,
                    "last_run_at": utcnow(),
                    "next_run_at": utcnow() + timedelta(seconds=interval),
                }
            },
        )

    async def _collect_from_source(
        self,
        client: Any,
        task: dict[str, Any],
        source: dict[str, Any],
        storage_channel: int,
        destinations: list[dict[str, Any]],
        runtime: dict[str, Any],
        remaining: int,
    ) -> int:
        raw = source.get("value")
        if not raw:
            return 0
        limit = max(remaining * 5, self.settings.task_batch_limit)
        kwargs: dict[str, Any] = {"limit": limit, "reverse": True}
        if source.get("last_message_id"):
            kwargs["min_id"] = int(source["last_message_id"])
        count = 0
        max_seen = int(source.get("last_message_id") or 0)
        async for message in client.iter_messages(raw, **kwargs):
            max_seen = max(max_seen, int(message.id))
            if count >= remaining:
                break
            if not message_has_video(message):
                continue
            created = await self._store_and_post(
                client=client,
                message=message,
                source_raw=raw,
                task=task,
                storage_channel=storage_channel,
                destinations=destinations,
                runtime=runtime,
            )
            if created:
                count += 1
        source["last_message_id"] = max_seen
        source["last_checked_at"] = utcnow()
        return count

    async def _store_and_post(
        self,
        client: Any,
        message: Any,
        source_raw: str,
        task: dict[str, Any],
        storage_channel: int,
        destinations: list[dict[str, Any]],
        runtime: dict[str, Any],
    ) -> bool:
        fingerprint = message_fingerprint(message)
        token = secrets.token_urlsafe(9).replace("-", "").replace("_", "")
        video_info = message_video_info(message)
        try:
            forwarded = await client.forward_messages(
                entity=int(storage_channel),
                messages=message,
                from_peer=source_raw,
                drop_author=not bool(runtime.get("forward_tag_enabled")),
            )
        except Exception as exc:
            await self.db.col("tasks").update_one(
                {"_id": task["_id"]}, {"$set": {"last_error": f"Storage forward failed: {exc}"}}
            )
            return False

        storage_message_id = int(getattr(forwarded, "id", 0) or 0)
        if not storage_message_id:
            return False
        media_doc = {
            "task_id": task["_id"],
            "task_name": task.get("name"),
            "fingerprint": fingerprint,
            "token": token,
            "source": source_raw,
            "source_message_id": int(message.id),
            "storage_chat_id": int(storage_channel),
            "storage_message_id": storage_message_id,
            "duration": video_info.get("duration"),
            "size": video_info.get("size"),
            "created_at": utcnow(),
        }
        try:
            await self.db.col("media").insert_one(media_doc)
        except DuplicateKeyError:
            return False

        thumb_bytes = await download_thumbnail_bytes(message)
        await self._post_destinations(media_doc, destinations, thumb_bytes, runtime)
        return True

    async def _post_destinations(
        self,
        media: dict[str, Any],
        destinations: list[dict[str, Any]],
        thumb_bytes: bytes | None,
        runtime: dict[str, Any],
    ) -> None:
        username = await self.bot_username()
        deep_link = f"https://t.me/{username}?start=get_{media['token']}"
        caption = self.destination_caption(media)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Get This Video", url=deep_link)]]
        )
        for destination in destinations:
            chat_id = int(destination["chat_id"])
            try:
                if thumb_bytes:
                    sent = await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=BufferedInputFile(thumb_bytes, filename="thumbnail.jpg"),
                        caption=caption,
                        reply_markup=markup,
                        has_spoiler=True,
                    )
                else:
                    sent = await self.bot.send_message(chat_id=chat_id, text=caption, reply_markup=markup)
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                await self.db.col("destination_posts").insert_one(
                    {
                        "media_token": media["token"],
                        "chat_id": chat_id,
                        "error": str(exc),
                        "created_at": utcnow(),
                    }
                )
                continue
            await self.db.col("destination_posts").insert_one(
                {
                    "media_token": media["token"],
                    "chat_id": chat_id,
                    "message_id": sent.message_id,
                    "created_at": utcnow(),
                }
            )
            await self._schedule_destination_delete(runtime, chat_id, sent.message_id)

    def destination_caption(self, media: dict[str, Any]) -> str:
        duration = human_seconds(media.get("duration"))
        size = media.get("size")
        size_text = "unknown"
        if size:
            mb = float(size) / (1024 * 1024)
            size_text = f"{mb:.2f} MB"
        return f"Video length: {duration}\nVideo size: {size_text}"

    async def _schedule_destination_delete(self, runtime: dict[str, Any], chat_id: int, message_id: int) -> None:
        settings = runtime.get("auto_delete") or {}
        if not settings.get("destination_enabled"):
            return
        seconds = int(settings.get("destination_seconds") or 0)
        if seconds <= 0:
            return
        await self.db.col("messages_to_delete").insert_one(
            {
                "chat_id": int(chat_id),
                "message_id": int(message_id),
                "kind": "destination",
                "due_at": utcnow() + timedelta(seconds=seconds),
                "done": False,
                "created_at": utcnow(),
            }
        )

    async def _finish_task_run(self, task: dict[str, Any], interval: int, error: str | None) -> None:
        await self.db.col("tasks").update_one(
            {"_id": task["_id"]},
            {
                "$set": {
                    "last_error": error,
                    "last_run_at": utcnow(),
                    "next_run_at": utcnow() + timedelta(seconds=interval),
                }
            },
        )

    async def _delete_loop(self) -> None:
        while True:
            await self.run_delete_due()
            await asyncio.sleep(20)

    async def run_delete_due(self) -> None:
        now = utcnow()
        cursor = self.db.col("messages_to_delete").find({"done": False, "due_at": {"$lte": now}}).limit(50)
        async for item in cursor:
            try:
                await self.bot.delete_message(chat_id=int(item["chat_id"]), message_id=int(item["message_id"]))
                update = {"done": True, "deleted_at": utcnow(), "error": None}
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                update = {"done": True, "error": str(exc), "deleted_at": utcnow()}
            await self.db.col("messages_to_delete").update_one({"_id": item["_id"]}, {"$set": update})

