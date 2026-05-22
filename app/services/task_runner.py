from __future__ import annotations

import asyncio
import logging
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
from app.timeutils import compact_dt, human_seconds, utcnow


ACTIVE_TASK = "active"
logger = logging.getLogger(__name__)


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
        logger.info(
            "task_scheduler_started poll_interval=%ss source_collect_interval=%ss source_harvest_limit=%s",
            self.settings.poll_interval_seconds,
            self.settings.source_collect_interval_seconds,
            self.settings.source_harvest_limit,
        )

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
            try:
                await self.run_due_tasks()
            except Exception:
                logger.exception("task_scheduler_loop_error")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    async def run_due_tasks(self) -> None:
        now = utcnow()
        cursor = self.db.col("tasks").find({}).sort("updated_at", -1).limit(50)
        scanned = 0
        due = 0
        async for task in cursor:
            scanned += 1
            status = task.get("status", "draft")
            post_due = self._is_due(task.get("next_run_at"), now)
            collect_due = self._is_due(task.get("next_collect_at"), now)
            logger.info(
                "task_scheduler_check task_id=%s name=%r status=%s now=%s next_run=%s next_collect=%s post_due=%s collect_due=%s",
                task.get("_id"),
                task.get("name"),
                status,
                compact_dt(now),
                compact_dt(task.get("next_run_at")),
                compact_dt(task.get("next_collect_at")),
                post_due,
                collect_due,
            )
            if status != ACTIVE_TASK:
                logger.info("task_scheduler_skip task_id=%s reason=status_%s", task.get("_id"), status)
                continue
            if not post_due and not collect_due:
                logger.info("task_scheduler_skip task_id=%s reason=not_due", task.get("_id"))
                continue
            due += 1
            logger.info(
                "task_scheduler_due task_id=%s post_due=%s collect_due=%s",
                task.get("_id"),
                post_due,
                collect_due,
            )
            try:
                await self.run_task(task, collect_due=collect_due, post_due=post_due)
            except Exception as exc:
                logger.exception("task_scheduler_task_error task_id=%s", task.get("_id"))
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
        logger.info("task_scheduler_tick_complete scanned=%s due=%s now=%s", scanned, due, compact_dt(now))

    def _is_due(self, value: Any, now: Any) -> bool:
        if value is None:
            return True
        if getattr(value, "tzinfo", None) is None:
            value = value.replace(tzinfo=now.tzinfo)
        return value <= now

    async def run_task(
        self,
        task: dict[str, Any],
        *,
        force: bool = False,
        collect_due: bool | None = None,
        post_due: bool | None = None,
    ) -> None:
        if task.get("status") != ACTIVE_TASK and not force:
            logger.info("task_cycle_skipped task_id=%s reason=status_%s", task.get("_id"), task.get("status"))
            return
        now = utcnow()
        collect_due = self._is_due(task.get("next_collect_at"), now) if collect_due is None else collect_due
        post_due = self._is_due(task.get("next_run_at"), now) if post_due is None else post_due
        if force:
            collect_due = True
            post_due = True
        interval = int(task.get("interval_seconds") or 300)
        posts_per_interval = int(task.get("posts_per_interval") or 1)
        runtime = await self.db.get_runtime_settings()
        logger.info(
            "task_cycle_started task_id=%s name=%r force=%s collect_due=%s post_due=%s interval=%ss amount=%s now=%s",
            task.get("_id"),
            task.get("name"),
            force,
            collect_due,
            post_due,
            interval,
            posts_per_interval,
            compact_dt(now),
        )

        storage_channel = fix_channel_id(task.get("storage_channel"))
        destinations = [d for d in task.get("destinations", []) if d.get("status", "active") == "active"]
        sources = [s for s in task.get("sources", []) if s.get("status", "active") == "active"]
        if not storage_channel:
            await self._finish_task_run(task, interval, "Task needs a storage channel")
            return

        saved = 0
        updated_sources = list(task.get("sources", []))
        source_error = None
        if collect_due and sources:
            userbot = UserbotService(self.db, self.settings)
            client = await userbot.client()
            if not client:
                source_error = "Userbot is not logged in or not configured"
                logger.info("task_collect_skipped task_id=%s reason=userbot_not_ready", task.get("_id"))
            else:
                logger.info(
                    "task_collect_started task_id=%s sources=%s storage_channel=%s harvest_limit=%s",
                    task.get("_id"),
                    len(sources),
                    storage_channel,
                    self.settings.source_harvest_limit,
                )
                for source in updated_sources:
                    if saved >= self.settings.source_harvest_limit:
                        break
                    if source.get("status", "active") != "active":
                        logger.info(
                            "task_source_skipped task_id=%s source=%r reason=status_%s",
                            task.get("_id"),
                            source.get("value"),
                            source.get("status"),
                        )
                        continue
                    count = await self._collect_from_source(
                        client=client,
                        task=task,
                        source=source,
                        storage_channel=storage_channel,
                        runtime=runtime,
                        remaining=self.settings.source_harvest_limit - saved,
                    )
                    saved += count
        elif collect_due:
            logger.info("task_collect_skipped task_id=%s reason=no_active_sources", task.get("_id"))

        posted = 0
        if post_due and destinations:
            logger.info(
                "task_destination_started task_id=%s destinations=%s amount=%s",
                task.get("_id"),
                len(destinations),
                posts_per_interval,
            )
            posted = await self.post_stored_to_destinations(task, destinations, runtime, posts_per_interval)
        elif post_due:
            logger.info("task_destination_skipped task_id=%s reason=no_active_destinations", task.get("_id"))

        update_doc: dict[str, Any] = {
            "sources": updated_sources,
            "last_error": source_error,
            "last_saved_count": saved,
            "last_post_count": posted,
            "last_run_at": utcnow(),
            "updated_at": utcnow(),
        }
        if collect_due:
            update_doc["next_collect_at"] = utcnow() + timedelta(seconds=self.settings.source_collect_interval_seconds)
        if post_due:
            update_doc["next_run_at"] = utcnow() + timedelta(seconds=interval)
        logger.info(
            "task_cycle_finished task_id=%s saved=%s posted=%s next_run=%s next_collect=%s error=%r",
            task.get("_id"),
            saved,
            posted,
            compact_dt(update_doc.get("next_run_at") or task.get("next_run_at")),
            compact_dt(update_doc.get("next_collect_at") or task.get("next_collect_at")),
            source_error,
        )
        await self.db.col("tasks").update_one({"_id": task["_id"]}, {"$set": update_doc})
        return

    async def _collect_from_source(
        self,
        client: Any,
        task: dict[str, Any],
        source: dict[str, Any],
        storage_channel: int,
        runtime: dict[str, Any],
        remaining: int,
    ) -> int:
        raw = fix_channel_id(source.get("value"))
        if not raw:
            return 0
        limit = max(remaining * 5, self.settings.task_batch_limit)
        kwargs: dict[str, Any] = {"limit": limit}
        if source.get("last_message_id"):
            kwargs["min_id"] = int(source["last_message_id"])
        count = 0
        seen = 0
        videos = 0
        duplicates = 0
        failed = 0
        max_seen = int(source.get("last_message_id") or 0)
        logger.info(
            "task_source_scan_started task_id=%s source=%r min_id=%s limit=%s remaining=%s storage_channel=%s",
            task.get("_id"),
            raw,
            source.get("last_message_id"),
            limit,
            remaining,
            storage_channel,
        )
        try:
            async for message in client.iter_messages(raw, **kwargs):
                seen += 1
                max_seen = max(max_seen, int(message.id))
                if count >= remaining:
                    break
                if not message_has_video(message):
                    continue
                videos += 1
                result = await self._store_source_message(
                    client=client,
                    message=message,
                    source_raw=raw,
                    task=task,
                    storage_channel=storage_channel,
                    runtime=runtime,
                )
                if result == "saved":
                    count += 1
                    if self.settings.source_collect_sleep_seconds:
                        await asyncio.sleep(self.settings.source_collect_sleep_seconds)
                elif result == "duplicate":
                    duplicates += 1
                else:
                    failed += 1
        except Exception as exc:
            source["last_error"] = f"Source scan failed: {exc}"
            source["last_checked_at"] = utcnow()
            logger.exception("task_source_scan_failed task_id=%s source=%r", task.get("_id"), raw)
            return count
        if failed == 0:
            source["last_message_id"] = max_seen
        else:
            source["last_error"] = f"{failed} storage failures; cursor not advanced"
        source["last_checked_at"] = utcnow()
        logger.info(
            "task_source_scan_finished task_id=%s source=%r seen=%s videos=%s saved=%s duplicates=%s failed=%s cursor=%s advanced=%s",
            task.get("_id"),
            raw,
            seen,
            videos,
            count,
            duplicates,
            failed,
            source.get("last_message_id"),
            failed == 0,
        )
        return count

    async def _store_source_message(
        self,
        client: Any,
        message: Any,
        source_raw: str,
        task: dict[str, Any],
        storage_channel: int,
        runtime: dict[str, Any],
    ) -> str:
        fingerprint = message_fingerprint(message)
        existing = await self.db.col("media").find_one({"fingerprint": fingerprint})
        if existing and existing.get("storage_status") != "failed":
            logger.info(
                "task_source_duplicate task_id=%s source=%r message_id=%s fingerprint=%s storage_status=%s destination_status=%s",
                task.get("_id"),
                source_raw,
                getattr(message, "id", None),
                fingerprint,
                existing.get("storage_status"),
                existing.get("destination_status"),
            )
            return "duplicate"
        token = secrets.token_urlsafe(9).replace("-", "").replace("_", "")
        video_info = message_video_info(message)
        media_doc = {
            "task_id": task["_id"],
            "task_name": task.get("name"),
            "fingerprint": fingerprint,
            "token": token,
            "source": source_raw,
            "source_message_id": int(message.id),
            "storage_chat_id": int(storage_channel),
            "storage_message_id": None,
            "duration": video_info.get("duration"),
            "size": video_info.get("size"),
            "storage_status": "reserved",
            "destination_status": "pending",
            "posted_destination_chat_ids": [],
            "created_at": utcnow(),
        }
        if existing:
            token = existing.get("token") or token
            media_doc["token"] = token
            await self.db.col("media").update_one(
                {"_id": existing["_id"]},
                {"$set": {**media_doc, "retry_at": utcnow(), "updated_at": utcnow()}},
            )
        else:
            try:
                await self.db.col("media").insert_one(media_doc)
            except DuplicateKeyError:
                return "duplicate"
        try:
            forwarded = await client.forward_messages(
                entity=chat_ref(storage_channel),
                messages=message,
                from_peer=source_raw,
                drop_author=not bool(runtime.get("forward_tag_enabled")),
            )
        except Exception as exc:
            await self.db.col("media").update_one(
                {"fingerprint": fingerprint},
                {"$set": {"storage_status": "failed", "last_error": f"Storage forward failed: {exc}", "updated_at": utcnow()}},
            )
            logger.exception(
                "task_storage_forward_failed task_id=%s source=%r message_id=%s storage_channel=%s fingerprint=%s",
                task.get("_id"),
                source_raw,
                getattr(message, "id", None),
                storage_channel,
                fingerprint,
            )
            return "failed"

        storage_message_id = int(getattr(forwarded, "id", 0) or 0)
        if not storage_message_id:
            await self.db.col("media").update_one(
                {"fingerprint": fingerprint},
                {"$set": {"storage_status": "failed", "last_error": "Storage forward returned no message id", "updated_at": utcnow()}},
            )
            logger.info(
                "task_storage_forward_failed task_id=%s source=%r message_id=%s reason=no_storage_message_id",
                task.get("_id"),
                source_raw,
                getattr(message, "id", None),
            )
            return "failed"

        thumb_bytes = await download_thumbnail_bytes(message)
        await self.db.col("media").update_one(
            {"fingerprint": fingerprint},
            {
                "$set": {
                    "storage_message_id": storage_message_id,
                    "storage_status": "stored",
                    "thumbnail_bytes": thumb_bytes,
                    "updated_at": utcnow(),
                }
            },
        )
        logger.info(
            "task_storage_saved task_id=%s source=%r source_message_id=%s storage_channel=%s storage_message_id=%s token=%s",
            task.get("_id"),
            source_raw,
            int(message.id),
            storage_channel,
            storage_message_id,
            token,
        )
        return "saved"

    async def post_stored_to_destinations(
        self,
        task: dict[str, Any],
        destinations: list[dict[str, Any]],
        runtime: dict[str, Any],
        limit: int,
    ) -> int:
        posted = 0
        pending = await self.db.col("media").count_documents(
            {"task_id": task["_id"], "storage_status": "stored", "destination_status": {"$ne": "posted"}}
        )
        logger.info(
            "task_destination_pending task_id=%s pending_media=%s limit=%s destinations=%s",
            task.get("_id"),
            pending,
            limit,
            len(destinations),
        )
        cursor = (
            self.db.col("media")
            .find({"task_id": task["_id"], "storage_status": "stored", "destination_status": {"$ne": "posted"}})
            .sort("created_at", 1)
            .limit(limit)
        )
        async for media in cursor:
            if await self._post_destinations(media, destinations, media.get("thumbnail_bytes"), runtime):
                posted += 1
        logger.info("task_destination_finished task_id=%s posted_media=%s", task.get("_id"), posted)
        return posted

    async def _post_destinations(
        self,
        media: dict[str, Any],
        destinations: list[dict[str, Any]],
        thumb_bytes: bytes | None,
        runtime: dict[str, Any],
    ) -> bool:
        username = await self.bot_username()
        if not username:
            logger.info("task_destination_skipped_media media_token=%s reason=bot_username_missing", media.get("token"))
            return False
        deep_link = f"https://t.me/{username}?start=get_{media['token']}"
        caption = self.destination_caption(media)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Get This Video", url=deep_link)]]
        )
        attempted = 0
        posted_chats = {chat_ref(value) for value in (media.get("posted_destination_chat_ids") or [])}
        for destination in destinations:
            chat_id = chat_ref(fix_channel_id(destination["chat_id"]))
            if chat_id in posted_chats:
                logger.info(
                    "task_destination_duplicate media_token=%s chat_id=%s reason=already_marked",
                    media.get("token"),
                    chat_id,
                )
                continue
            existing = await self.db.col("destination_posts").find_one({"media_token": media["token"], "chat_id": chat_id})
            if existing and existing.get("message_id"):
                posted_chats.add(chat_id)
                logger.info(
                    "task_destination_duplicate media_token=%s chat_id=%s reason=existing_message",
                    media.get("token"),
                    chat_id,
                )
                continue
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
                logger.info(
                    "task_destination_post_failed media_token=%s chat_id=%s error=%s",
                    media.get("token"),
                    chat_id,
                    exc,
                )
                await self.db.col("destination_posts").update_one(
                    {"media_token": media["token"], "chat_id": chat_id},
                    {"$set": {"error": str(exc), "updated_at": utcnow()}, "$setOnInsert": {"created_at": utcnow()}},
                    upsert=True,
                )
                continue
            await self.db.col("destination_posts").update_one(
                {"media_token": media["token"], "chat_id": chat_id},
                {
                    "$set": {"message_id": sent.message_id, "error": None, "updated_at": utcnow()},
                    "$setOnInsert": {"created_at": utcnow()},
                },
                upsert=True,
            )
            attempted += 1
            posted_chats.add(chat_id)
            logger.info(
                "task_destination_posted media_token=%s chat_id=%s message_id=%s",
                media.get("token"),
                chat_id,
                sent.message_id,
            )
            await self._schedule_destination_delete(runtime, chat_id, sent.message_id)
        destination_status = "posted" if all(chat_ref(d["chat_id"]) in posted_chats for d in destinations) else "partial"
        await self.db.col("media").update_one(
            {"_id": media["_id"]},
            {
                "$set": {
                    "destination_status": destination_status,
                    "posted_destination_chat_ids": list(posted_chats),
                    "destination_posted_at": utcnow() if destination_status == "posted" else media.get("destination_posted_at"),
                }
            },
        )
        logger.info(
            "task_destination_media_finished media_token=%s attempted=%s status=%s posted_chats=%s",
            media.get("token"),
            attempted,
            destination_status,
            len(posted_chats),
        )
        return attempted > 0

    def destination_caption(self, media: dict[str, Any]) -> str:
        duration = human_seconds(media.get("duration"))
        size = media.get("size")
        size_text = "unknown"
        if size:
            mb = float(size) / (1024 * 1024)
            size_text = f"{mb:.2f} MB"
        return f"Video length: {duration}\nVideo size: {size_text}"

    async def _schedule_destination_delete(self, runtime: dict[str, Any], chat_id: int | str, message_id: int) -> None:
        settings = runtime.get("auto_delete") or {}
        if not settings.get("destination_enabled"):
            return
        seconds = int(settings.get("destination_seconds") or 0)
        if seconds <= 0:
            return
        await self.db.col("messages_to_delete").insert_one(
            {
                    "chat_id": chat_id,
                "message_id": int(message_id),
                "kind": "destination",
                "due_at": utcnow() + timedelta(seconds=seconds),
                "done": False,
                "created_at": utcnow(),
            }
        )

    async def _finish_task_run(self, task: dict[str, Any], interval: int, error: str | None) -> None:
        logger.info("task_cycle_finished task_id=%s skipped_reason=%r", task.get("_id"), error)
        await self.db.col("tasks").update_one(
            {"_id": task["_id"]},
            {
                "$set": {
                    "last_error": error,
                    "last_run_at": utcnow(),
                    "next_run_at": utcnow() + timedelta(seconds=interval),
                    "next_collect_at": utcnow() + timedelta(seconds=self.settings.source_collect_interval_seconds),
                    "updated_at": utcnow(),
                }
            },
        )

    async def _delete_loop(self) -> None:
        while True:
            try:
                await self.run_delete_due()
            except Exception:
                logger.exception("task_delete_loop_error")
            await asyncio.sleep(20)

    async def run_delete_due(self) -> None:
        now = utcnow()
        cursor = self.db.col("messages_to_delete").find({"done": False, "due_at": {"$lte": now}}).limit(50)
        async for item in cursor:
            try:
                await self.bot.delete_message(chat_id=chat_ref(item["chat_id"]), message_id=int(item["message_id"]))
                update = {"done": True, "deleted_at": utcnow(), "error": None}
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                update = {"done": True, "error": str(exc), "deleted_at": utcnow()}
            await self.db.col("messages_to_delete").update_one({"_id": item["_id"]}, {"$set": update})


def fix_channel_id(value: Any) -> int | str:
    if value is None:
        return None
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        if s.startswith("-100"):
            return int(s)
        if s.startswith("-"):
            return int(f"-100{s.lstrip('-')}")
        return int(f"-100{s}")
    return value


def chat_ref(value: Any) -> int | str:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return str(value)
