from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from bson import ObjectId

from app.callbacks import (
    ACCESS_HOME,
    ADMIN_HOME,
    AUTO_DELETE_HOME,
    BROADCAST_HOME,
    FORCE_HOME,
    FORWARD_TAG_TOGGLE,
    TASKS_HOME,
    USERBOT_HOME,
    cb,
    split_cb,
)
from app.config import Settings
from app.database import Database
from app.guards import reject_callback_if_not_admin, reject_message_if_not_admin
from app.services.force_subscription import ForceSubscriptionService
from app.services.state import AdminStateStore
from app.services.task_runner import TaskScheduler, fix_channel_id
from app.services.userbot import UserbotService
from app.timeutils import utcnow
from app.ui import keyboards, text


router = Router(name="admin")


@router.message(Command("admin"))
async def admin_command(message: Message, db: Database, settings: Settings) -> None:
    if await reject_message_if_not_admin(message, settings):
        return
    await message.answer(
        text.admin_home(await admin_stats(db), await db.get_runtime_settings()),
        reply_markup=keyboards.admin_home_keyboard(),
    )


@router.callback_query(F.data == ADMIN_HOME)
async def admin_home_callback(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await safe_edit(
        query,
        text.admin_home(await admin_stats(db), await db.get_runtime_settings()),
        keyboards.admin_home_keyboard(),
    )


@router.callback_query(F.data == FORWARD_TAG_TOGGLE)
async def toggle_forward_tag(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    runtime = await db.get_runtime_settings()
    enabled = not bool(runtime.get("forward_tag_enabled"))
    await db.set_runtime_path("forward_tag_enabled", enabled)
    await query.answer(f"Forward tag {'on' if enabled else 'off'}")
    await safe_edit(
        query,
        text.admin_home(await admin_stats(db), await db.get_runtime_settings()),
        keyboards.admin_home_keyboard(),
    )


@router.callback_query(F.data == USERBOT_HOME)
async def userbot_home(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    service = UserbotService(db, settings)
    doc = await service.session_doc()
    await safe_edit(
        query,
        text.userbot_home(doc, await service.has_credentials()),
        keyboards.userbot_keyboard(bool(doc.get("session_string"))),
    )


@router.callback_query(F.data == cb("userbot", "login"))
async def userbot_login(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await AdminStateStore(db).set(query.from_user.id, "userbot_api_id", {"next": "string"})
    await query.message.answer("⌨️ <b>Send the Telegram API ID</b> for the userbot account.\n\n<i>Send /cancel to stop.</i>")


@router.callback_query(F.data == cb("userbot", "phone"))
async def userbot_phone_login(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await AdminStateStore(db).set(query.from_user.id, "userbot_api_id", {"next": "phone"})
    await query.message.answer("⌨️ <b>Send the Telegram API ID</b> for the userbot account.\n\n<i>Send /cancel to stop.</i>")


@router.callback_query(F.data == cb("userbot", "logout"))
async def userbot_logout(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await UserbotService(db, settings).logout()
    await query.answer("Userbot logged out")
    doc = await UserbotService(db, settings).session_doc()
    service = UserbotService(db, settings)
    await safe_edit(query, text.userbot_home(doc, await service.has_credentials()), keyboards.userbot_keyboard(False))


@router.callback_query(F.data == TASKS_HOME)
async def tasks_home(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    tasks = await list_tasks(db)
    await safe_edit(query, text.tasks_home(tasks), keyboards.tasks_home_keyboard(tasks))


@router.callback_query(F.data == cb("task", "new"))
async def task_new(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await AdminStateStore(db).set(query.from_user.id, "task_new")
    await query.message.answer("⌨️ <b>Send the name for the new task</b>.\n\n<i>Send /cancel to stop.</i>")


@router.callback_query(F.data.startswith("task:"))
async def task_callbacks(
    query: CallbackQuery,
    db: Database,
    settings: Settings,
    scheduler: TaskScheduler | None = None,
) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    parts = split_cb(query.data)
    action = parts[1] if len(parts) > 1 else ""
    if action == "open" and len(parts) >= 3:
        await query.answer()
        await show_task(query, db, parts[2])
        return
    if action == "srcs" and len(parts) >= 3:
        await query.answer()
        await show_task_sources(query, db, parts[2])
        return
    if action == "dsts" and len(parts) >= 3:
        await query.answer()
        await show_task_destinations(query, db, parts[2])
        return
    if action == "src" and len(parts) >= 4:
        await query.answer()
        await show_task_source(query, db, parts[2], int(parts[3]))
        return
    if action == "dst" and len(parts) >= 4:
        await query.answer()
        await show_task_destination(query, db, parts[2], int(parts[3]))
        return
    if action in {"addsrc", "adddst", "storage", "interval", "amount"} and len(parts) >= 3:
        prompts = {
            "addsrc": "📥 <b>Send source details:</b>\nProvide a numeric ID, @username, or t.me link. You can also forward a message from the source channel.",
            "adddst": "📤 <b>Send destination details:</b>\nProvide it as: <code>chat_id | title | public_link</code>, or forward a message from the destination channel.",
            "storage": "📦 <b>Send storage channel details:</b>\nProvide the numeric ID or forward a message from the storage channel.",
            "interval": "⏱️ <b>Set run interval:</b>\nChoose a preset below, or send a custom interval (e.g., <i>1 minute, 5m, 30m, 1 hour, 1d</i>).",
            "amount": "🔢 <b>Set post amount:</b>\nChoose a preset below, or send a custom number of posts per interval.",
        }
        await query.answer()
        await AdminStateStore(db).set(query.from_user.id, f"task_{action}", {"task_id": parts[2]})
        if action == "interval":
            await query.message.answer(
                f"{prompts[action]}\n\n<i>Send /cancel to stop.</i>",
                reply_markup=keyboards.task_interval_keyboard(parts[2]),
            )
        elif action == "amount":
            await query.message.answer(
                f"{prompts[action]}\n\n<i>Send /cancel to stop.</i>",
                reply_markup=keyboards.task_amount_keyboard(parts[2]),
            )
        else:
            await query.message.answer(f"{prompts[action]}\n\n<i>Send /cancel to stop.</i>")
        return
    if action == "setint" and len(parts) >= 4:
        seconds = int(parts[3])
        await db.col("tasks").update_one(
            {"_id": ObjectId(parts[2])},
            {"$set": {"interval_seconds": seconds, "next_run_at": utcnow() + timedelta(seconds=seconds), "updated_at": utcnow()}},
        )
        await query.answer("Interval saved")
        await AdminStateStore(db).clear(query.from_user.id)
        await show_task(query, db, parts[2])
        return
    if action == "setamt" and len(parts) >= 4:
        amount = int(parts[3])
        await db.col("tasks").update_one(
            {"_id": ObjectId(parts[2])},
            {"$set": {"posts_per_interval": amount, "updated_at": utcnow()}},
        )
        await query.answer("Post amount saved")
        await AdminStateStore(db).clear(query.from_user.id)
        await show_task(query, db, parts[2])
        return
    if action == "runnow" and len(parts) >= 3:
        if not scheduler:
            await query.answer("Scheduler is not running", show_alert=True)
            return
        await query.answer("Manual run started")
        asyncio.create_task(run_manual_with_progress_edit(query, db, scheduler, parts[2]))
        return
    if action == "clearstorage" and len(parts) >= 3:
        await db.col("tasks").update_one(
            {"_id": ObjectId(parts[2])}, {"$set": {"storage_channel": None, "updated_at": utcnow()}}
        )
        await query.answer("Storage removed")
        await show_task(query, db, parts[2])
        return
    if action in {"srcedit", "dstedit"} and len(parts) >= 4:
        prompt = (
            "📝 <b>Send replacement source details:</b>\nProvide a numeric ID, @username, or t.me link."
            if action == "srcedit"
            else "📝 <b>Send replacement destination details:</b>\nProvide it as: <code>chat_id | title | public_link</code>."
        )
        await query.answer()
        await AdminStateStore(db).set(
            query.from_user.id,
            f"task_{action}",
            {"task_id": parts[2], "index": int(parts[3])},
        )
        await query.message.answer(f"{prompt}\n\n<i>Send /cancel to stop.</i>")
        return
    if action in {"srcpau", "srcres", "srcrm", "dstpau", "dstres", "dstrm"} and len(parts) >= 4:
        await update_task_item_control(db, parts[2], int(parts[3]), action)
        await query.answer("Updated")
        if action.startswith("src"):
            await show_task_sources(query, db, parts[2])
        else:
            await show_task_destinations(query, db, parts[2])
        return
    if action in {"pause", "resume", "stop"} and len(parts) >= 3:
        status = "active" if action == "resume" else "paused"
        update_fields: dict[str, Any] = {
            "status": status,
            "updated_at": utcnow(),
        }
        if status == "active":
            update_fields["next_run_at"] = utcnow()
            update_fields["next_collect_at"] = utcnow()
            update_fields["last_error"] = None
        else:
            update_fields["next_run_at"] = None
            update_fields["next_collect_at"] = None

        await db.col("tasks").update_one(
            {"_id": ObjectId(parts[2])},
            {"$set": update_fields}
        )
        await query.answer(f"Auto-posting {'started' if status == 'active' else 'paused'}")
        await show_task(query, db, parts[2])
        return
    await query.answer("Unknown task action", show_alert=True)


@router.callback_query(F.data == FORCE_HOME)
async def force_home(query: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    targets = await ForceSubscriptionService(db, bot).targets()
    await safe_edit(query, text.force_home(targets), keyboards.force_targets_keyboard(targets))


@router.callback_query(F.data.startswith("force:"))
async def force_callbacks(query: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    service = ForceSubscriptionService(db, bot)
    parts = split_cb(query.data)
    action = parts[1] if len(parts) > 1 else ""
    if action == "add":
        await query.answer()
        await AdminStateStore(db).set(query.from_user.id, "force_add")
        await query.message.answer(
            "➕ <b>Send force subscription channel details:</b>\n"
            "Format: <code>chat_id | title | join/request | invite_link(optional)</code>\n\n"
            "<i>Note: Forwarded channel messages are also supported when Telegram exposes the chat. Send /cancel to stop.</i>"
        )
        return
    if action == "target" and len(parts) >= 3:
        await query.answer()
        target = await db.col("force_targets").find_one({"chat_id": int(parts[2])})
        if target:
            await safe_edit(query, text.force_home([target]), keyboards.force_target_keyboard(target))
        return
    if action in {"toggle", "refresh", "remove"} and len(parts) >= 3:
        chat_id = int(parts[2])
        if action == "toggle":
            await service.toggle_enabled(chat_id)
        elif action == "refresh":
            await service.refresh_invite_link(chat_id)
        else:
            await service.remove_target(chat_id)
        await query.answer("Updated")
        targets = await service.targets()
        await safe_edit(query, text.force_home(targets), keyboards.force_targets_keyboard(targets))
        return
    if action == "mode" and len(parts) >= 4:
        await service.set_mode(int(parts[2]), parts[3])
        await query.answer("Mode updated")
        target = await db.col("force_targets").find_one({"chat_id": int(parts[2])})
        if target:
            await safe_edit(query, text.force_home([target]), keyboards.force_target_keyboard(target))
        return
    await query.answer("Unknown force subscription action", show_alert=True)


@router.callback_query(F.data == ACCESS_HOME)
async def access_home(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await safe_edit(query, text.access_home(await db.get_runtime_settings()), keyboards.access_keyboard())


@router.callback_query(F.data.startswith("access:"))
async def access_callbacks(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    parts = split_cb(query.data)
    action = parts[1] if len(parts) > 1 else ""
    states = {
        "limit": "access_limit",
        "premium": "access_premium",
        "refchan": "access_refchan",
        "refrule": "access_refrule",
    }
    prompts = {
        "limit": "🔢 <b>Send free daily limit:</b>\nProvide a number (e.g., <i>5, 10, or 15</i>).",
        "premium": "💎 <b>Send premium access grant:</b>\nProvide as: <code>user_id days</code> (e.g., <i>123456789 30</i>).",
        "refchan": "📢 <b>Send referral channel ID:</b>\nProvide the numeric ID of the referral group/channel.",
        "refrule": "⚙️ <b>Send referral rule details:</b>\nProvide as: <code>required_joins reward_limit reward_days</code> (e.g., <i>10 100 5</i>).",
    }
    if action in states:
        await query.answer()
        await AdminStateStore(db).set(query.from_user.id, states[action])
        await query.message.answer(f"{prompts[action]}\n\n<i>Send /cancel to stop.</i>")
        return
    await query.answer("Unknown access action", show_alert=True)


@router.callback_query(F.data == AUTO_DELETE_HOME)
async def auto_delete_home(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await safe_edit(query, text.auto_delete_home(await db.get_runtime_settings()), keyboards.auto_delete_keyboard())


@router.callback_query(F.data.startswith("autodel:"))
async def auto_delete_callbacks(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    parts = split_cb(query.data)
    action = parts[1] if len(parts) > 1 else ""
    target = parts[2] if len(parts) > 2 else ""
    if target not in {"destination", "delivery"}:
        await query.answer("Invalid auto-delete target", show_alert=True)
        return
    runtime = await db.get_runtime_settings()
    settings_doc = runtime.get("auto_delete") or {}
    if action == "toggle":
        key = f"{target}_enabled"
        await db.set_runtime_path(f"auto_delete.{key}", not bool(settings_doc.get(key)))
        await query.answer("Updated")
        await safe_edit(query, text.auto_delete_home(await db.get_runtime_settings()), keyboards.auto_delete_keyboard())
        return
    if action == "time":
        await query.answer()
        await AdminStateStore(db).set(query.from_user.id, "autodel_time", {"target": target})
        await query.message.answer("⏱️ <b>Send auto-delete duration:</b>\nFormat: <i>10m, 1h, 1d</i> or seconds.\n\n<i>Send /cancel to stop.</i>")
        return
    await query.answer("Unknown auto-delete action", show_alert=True)


@router.callback_query(F.data == BROADCAST_HOME)
async def broadcast_home(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await safe_edit(query, text.broadcast_home(await broadcast_stats(db)), keyboards.broadcast_keyboard())


@router.callback_query(F.data == cb("broadcast", "new"))
async def broadcast_new(query: CallbackQuery, db: Database, settings: Settings) -> None:
    if await reject_callback_if_not_admin(query, settings):
        return
    await query.answer()
    await AdminStateStore(db).set(query.from_user.id, "broadcast_new")
    await query.message.answer("📣 <b>Send or forward the message to broadcast:</b>\nIt will be cloned and copied to all saved users.\n\n<i>Send /cancel to stop.</i>")


@router.message(Command("cancel"))
async def cancel_state(message: Message, db: Database, settings: Settings) -> None:
    if await reject_message_if_not_admin(message, settings):
        return
    await AdminStateStore(db).clear(message.from_user.id)
    await message.answer("Cancelled.", reply_markup=keyboards.home_back_keyboard())


@router.message()
async def admin_state_message(message: Message, db: Database, bot: Bot, settings: Settings) -> None:
    if not message.from_user or message.from_user.id not in settings.manager_ids:
        return
    state_store = AdminStateStore(db)
    state = await state_store.get(message.from_user.id)
    if not state:
        return
    name = state.get("name")
    payload = state.get("payload") or {}
    clear_state = True
    try:
        if name == "userbot_login":
            await handle_userbot_login(message, db, settings)
        elif name == "userbot_api_id":
            clear_state = await handle_userbot_api_id(message, db)
        elif name == "userbot_api_hash":
            clear_state = await handle_userbot_api_hash(message, db, settings, payload)
        elif name == "userbot_phone":
            clear_state = await handle_userbot_phone(message, db, settings)
        elif name == "userbot_code":
            clear_state = await handle_userbot_code(message, db, settings, payload)
        elif name == "userbot_password":
            await handle_userbot_password(message, db, settings)
        elif name == "task_new":
            await handle_task_new(message, db)
        elif name and name.startswith("task_"):
            await handle_task_update(message, db, name, payload)
        elif name == "force_add":
            await handle_force_add(message, db, bot)
        elif name in {"access_limit", "access_premium", "access_refchan", "access_refrule"}:
            await handle_access_update(message, db, name)
        elif name == "autodel_time":
            await handle_autodel_time(message, db, payload)
        elif name == "broadcast_new":
            await handle_broadcast(message, db, bot)
        else:
            await message.answer("Unknown pending action. Use /cancel and try again.")
            return
    except ValueError as exc:
        await message.answer(f"Invalid input: {exc}")
        return
    except Exception as exc:
        await message.answer(f"Action failed: {exc}")
        return
    if clear_state:
        await state_store.clear(message.from_user.id)


async def handle_userbot_login(message: Message, db: Database, settings: Settings) -> None:
    session_string = (message.text or "").strip()
    if len(session_string) < 50:
        raise ValueError("session string is too short")
    await UserbotService(db, settings).save_session_string(session_string)
    await message.answer("Userbot session saved.", reply_markup=keyboards.home_back_keyboard())


async def handle_userbot_api_id(message: Message, db: Database) -> bool:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        raise ValueError("API ID must be numeric")
    state = await AdminStateStore(db).get(message.from_user.id)
    payload = dict((state or {}).get("payload") or {})
    payload["api_id"] = int(raw)
    await AdminStateStore(db).set(message.from_user.id, "userbot_api_hash", payload)
    await message.answer("✅ <b>API ID saved.</b>\nNow send the Telegram API Hash.\n\n<i>Send /cancel to stop.</i>")
    return False


async def handle_userbot_api_hash(message: Message, db: Database, settings: Settings, payload: dict[str, Any]) -> bool:
    api_hash = (message.text or "").strip()
    if len(api_hash) < 8:
        raise ValueError("API Hash looks too short")
    await UserbotService(db, settings).save_credentials(int(payload["api_id"]), api_hash)
    next_step = payload.get("next") or "phone"
    if next_step == "string":
        await AdminStateStore(db).set(message.from_user.id, "userbot_login")
        await message.answer("✅ <b>API Hash saved.</b>\nNow paste the Telethon StringSession string.\n\n<i>Send /cancel to stop.</i>")
    else:
        await AdminStateStore(db).set(message.from_user.id, "userbot_phone")
        await message.answer("✅ <b>API Hash saved.</b>\nNow send the phone number in international format (e.g., <code>+911234567890</code>).\n\n<i>Send /cancel to stop.</i>")
    return False


async def handle_userbot_phone(message: Message, db: Database, settings: Settings) -> bool:
    phone = (message.text or "").strip()
    if not phone.startswith("+") or len(phone) < 8:
        raise ValueError("send a phone number like +911234567890")
    attempt = await UserbotService(db, settings).start_phone_login(phone)
    await AdminStateStore(db).set(message.from_user.id, "userbot_code", attempt)
    await message.answer("📥 <b>Login code sent on Telegram.</b>\nEnter the numeric code here.\n\n<i>Send /cancel to stop.</i>")
    return False


async def handle_userbot_code(message: Message, db: Database, settings: Settings, payload: dict[str, Any]) -> bool:
    code = re.sub(r"\D+", "", message.text or "")
    if len(code) < 4:
        raise ValueError("send the numeric login code")
    completed = await UserbotService(db, settings).complete_phone_code(
        phone=payload["phone"],
        code=code,
        phone_code_hash=payload["phone_code_hash"],
        session_string=payload["session_string"],
    )
    if completed:
        await message.answer("Userbot login completed.", reply_markup=keyboards.home_back_keyboard())
        return True
    await AdminStateStore(db).set(message.from_user.id, "userbot_password")
    await message.answer("🔐 <b>2FA protection detected.</b>\nEnter the account 2FA password.\n\n<i>Send /cancel to stop.</i>")
    return False


async def handle_userbot_password(message: Message, db: Database, settings: Settings) -> None:
    password = message.text or ""
    if not password:
        raise ValueError("send the 2FA password")
    await UserbotService(db, settings).complete_password(password)
    await message.answer("Userbot login completed.", reply_markup=keyboards.home_back_keyboard())


async def handle_task_new(message: Message, db: Database) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        raise ValueError("task name is too short")
    doc = {
        "name": name[:80],
        "status": "draft",
        "sources": [],
        "destinations": [],
        "storage_channel": None,
        "interval_seconds": 300,
        "posts_per_interval": 1,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    result = await db.col("tasks").insert_one(doc)
    await show_task_details_view(message, db, result.inserted_id)


async def handle_task_update(message: Message, db: Database, name: str, payload: dict[str, Any]) -> None:
    task_id = ObjectId(payload["task_id"])
    task = await db.col("tasks").find_one({"_id": task_id})
    if not task:
        raise ValueError("task not found")
    if name == "task_addsrc":
        value, title, _ = parse_channel_like_input(message, require_numeric=False)
        source = {"value": value, "title": title or str(value), "status": "active", "added_at": utcnow()}
        await db.col("tasks").update_one({"_id": task_id}, {"$push": {"sources": source}, "$set": {"updated_at": utcnow()}})
        await message.answer("Source added.")
    elif name == "task_srcedit":
        index = int(payload["index"])
        sources = list(task.get("sources", []))
        if index < 0 or index >= len(sources):
            raise ValueError("source not found")
        value, title, _ = parse_channel_like_input(message, require_numeric=False)
        sources[index].update({"value": value, "title": title or str(value), "updated_at": utcnow()})
        await db.col("tasks").update_one({"_id": task_id}, {"$set": {"sources": sources, "updated_at": utcnow()}})
        await message.answer("Source updated.")
    elif name == "task_adddst":
        value, title, link = parse_channel_like_input(message, require_numeric=False)
        destination = {"chat_id": value, "title": title or str(value), "link": link, "status": "active", "added_at": utcnow()}
        await db.col("tasks").update_one(
            {"_id": task_id},
            {"$push": {"destinations": destination}, "$set": {"updated_at": utcnow()}},
        )
        await add_runtime_destination(db, destination)
        await message.answer("Destination added.")
    elif name == "task_dstedit":
        index = int(payload["index"])
        destinations = list(task.get("destinations", []))
        if index < 0 or index >= len(destinations):
            raise ValueError("destination not found")
        value, title, link = parse_channel_like_input(message, require_numeric=False)
        destinations[index].update({"chat_id": value, "title": title or str(value), "link": link, "updated_at": utcnow()})
        await db.col("tasks").update_one(
            {"_id": task_id}, {"$set": {"destinations": destinations, "updated_at": utcnow()}}
        )
        await add_runtime_destination(db, destinations[index])
        await message.answer("Destination updated.")
    elif name == "task_storage":
        value, _, _ = parse_channel_like_input(message, require_numeric=False)
        await db.col("tasks").update_one(
            {"_id": task_id}, {"$set": {"storage_channel": value, "updated_at": utcnow()}}
        )
        await message.answer("Storage channel saved.")
    elif name == "task_interval":
        seconds = parse_duration_seconds(message.text or "")
        await db.col("tasks").update_one(
            {"_id": task_id},
            {"$set": {"interval_seconds": seconds, "next_run_at": utcnow() + timedelta(seconds=seconds), "updated_at": utcnow()}},
        )
        await message.answer("Interval updated.")
    elif name == "task_amount":
        amount = int((message.text or "").strip())
        if amount < 1 or amount > 100:
            raise ValueError("amount must be between 1 and 100")
        await db.col("tasks").update_one(
            {"_id": task_id}, {"$set": {"posts_per_interval": amount, "updated_at": utcnow()}}
        )
        await message.answer("Videos per interval updated.")
    await show_task_details_view(message, db, task_id)


async def handle_force_add(message: Message, db: Database, bot: Bot) -> None:
    value, title, link, mode = parse_force_input(message)
    target = await ForceSubscriptionService(db, bot).add_target(int(value), title=title, mode=mode, invite_link=link)
    await message.answer(text.force_home([target]), reply_markup=keyboards.force_target_keyboard(target))


async def handle_access_update(message: Message, db: Database, name: str) -> None:
    raw = (message.text or "").strip()
    if name == "access_limit":
        limit = int(raw)
        if limit < 1 or limit > 100000:
            raise ValueError("limit must be between 1 and 100000")
        await db.set_runtime_path("access.free_daily_limit", limit)
        await message.answer("Free daily limit updated.", reply_markup=keyboards.home_back_keyboard())
    elif name == "access_premium":
        numbers = [int(part) for part in re.split(r"[\s,|]+", raw) if part]
        if len(numbers) != 2:
            raise ValueError("send exactly 2 numbers: user_id days")
        user_id, days = numbers
        if days < 1:
            raise ValueError("days must be positive")
        await db.col("users").update_one(
            {"telegram_id": int(user_id)},
            {
                "$set": {
                    "telegram_id": int(user_id),
                    "plan": "premium",
                    "premium_until": utcnow() + timedelta(days=days),
                    "updated_at": utcnow(),
                },
                "$setOnInsert": {"first_seen_at": utcnow()},
            },
            upsert=True,
        )
        await message.answer("Premium granted.", reply_markup=keyboards.home_back_keyboard())
    elif name == "access_refchan":
        channel_id = int(fix_channel_id(raw))
        await db.set_runtime_path("referral.channel_id", channel_id)
        await message.answer("Referral channel updated.", reply_markup=keyboards.home_back_keyboard())
    elif name == "access_refrule":
        numbers = [int(part) for part in re.split(r"[\s,|]+", raw) if part]
        if len(numbers) != 3:
            raise ValueError("send exactly 3 numbers: required_joins reward_limit reward_days")
        await db.set_runtime_path("referral.required_joins", numbers[0])
        await db.set_runtime_path("referral.reward_limit", numbers[1])
        await db.set_runtime_path("referral.reward_days", numbers[2])
        await message.answer("Referral rule updated.", reply_markup=keyboards.home_back_keyboard())


async def handle_autodel_time(message: Message, db: Database, payload: dict[str, Any]) -> None:
    target = payload.get("target")
    if target not in {"destination", "delivery"}:
        raise ValueError("invalid target")
    seconds = parse_duration_seconds(message.text or "")
    await db.set_runtime_path(f"auto_delete.{target}_seconds", seconds)
    await message.answer("Auto-delete time updated.", reply_markup=keyboards.home_back_keyboard())


async def handle_broadcast(message: Message, db: Database, bot: Bot) -> None:
    broadcast = {
        "admin_chat_id": message.chat.id,
        "source_message_id": message.message_id,
        "status": "running",
        "total": await db.col("users").count_documents({}),
        "sent": 0,
        "failed": 0,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    result = await db.col("broadcasts").insert_one(broadcast)
    status_message = await message.answer("Broadcast started.\nSent: 0\nFailed: 0")
    asyncio.create_task(run_broadcast(db, bot, result.inserted_id, message.chat.id, message.message_id, status_message.chat.id, status_message.message_id))


async def run_broadcast(
    db: Database,
    bot: Bot,
    broadcast_id: ObjectId,
    source_chat_id: int,
    source_message_id: int,
    status_chat_id: int,
    status_message_id: int,
) -> None:
    sent = 0
    failed = 0
    cursor = db.col("users").find({}, {"telegram_id": 1, "user_id": 1, "id": 1}).sort("telegram_id", 1)
    async for user in cursor:
        target_id = extract_telegram_id(user)
        if not target_id:
            failed += 1
            continue
        try:
            await bot.copy_message(
                chat_id=target_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 25 == 0:
            await update_broadcast_progress(db, bot, broadcast_id, status_chat_id, status_message_id, sent, failed, False)
        await asyncio.sleep(0.04)
    await update_broadcast_progress(db, bot, broadcast_id, status_chat_id, status_message_id, sent, failed, True)


async def update_broadcast_progress(
    db: Database,
    bot: Bot,
    broadcast_id: ObjectId,
    chat_id: int,
    message_id: int,
    sent: int,
    failed: int,
    done: bool,
) -> None:
    status = "completed" if done else "running"
    processed = sent + failed
    doc = await db.col("broadcasts").find_one({"_id": broadcast_id}) or {}
    total = int(doc.get("total") or processed)
    remaining = max(0, total - processed)
    await db.col("broadcasts").update_one(
        {"_id": broadcast_id},
        {"$set": {"sent": sent, "failed": failed, "status": status, "updated_at": utcnow()}},
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                f"Broadcast {status}.\n"
                f"Total users: {total}\n"
                f"Processed: {processed}\n"
                f"Sent: {sent}\n"
                f"Failed: {failed}\n"
                f"Remaining: {remaining}"
            ),
        )
    except Exception:
        pass


async def admin_stats(db: Database) -> dict[str, int]:
    return {
        "users": await db.col("users").count_documents({}),
        "tasks": await db.col("tasks").count_documents({"status": "active"}),
        "all_tasks": await db.col("tasks").count_documents({}),
        "force_targets": await db.col("force_targets").count_documents({}),
        "media": await db.col("media").count_documents({}),
    }


async def broadcast_stats(db: Database) -> dict[str, int]:
    return {
        "users": await db.col("users").count_documents({}),
        "broadcasts": await db.col("broadcasts").count_documents({}),
    }


async def list_tasks(db: Database) -> list[dict[str, Any]]:
    cursor = db.col("tasks").find({}).sort("created_at", -1).limit(30)
    return [doc async for doc in cursor]


async def render_task_detail(
    db: Database,
    task_id: str | ObjectId,
) -> tuple[str, Any]:
    task = await db.col("tasks").find_one({"_id": ObjectId(task_id)})
    if not task:
        return "Task not found", None
    
    pending_count = await db.col("media").count_documents({
        "task_id": task["_id"],
        "storage_status": "stored",
        "destination_status": "pending",
    })
    
    last_posted_doc = await db.col("media").find_one(
        {"task_id": task["_id"], "destination_status": "posted"},
        sort=[("destination_posted_at", -1), ("created_at", -1)]
    )
    last_posted_token = last_posted_doc.get("token") if last_posted_doc else None
    
    body = text.task_detail(task, pending_count, last_posted_token)
    markup = keyboards.task_detail_keyboard(task)
    return body, markup


async def show_task_details_view(
    query_or_message: CallbackQuery | Message,
    db: Database,
    task_id: str | ObjectId,
) -> None:
    body, markup = await render_task_detail(db, task_id)
    if not markup:
        if isinstance(query_or_message, CallbackQuery):
            await query_or_message.answer(body, show_alert=True)
        else:
            await query_or_message.answer(body)
        return
        
    if isinstance(query_or_message, CallbackQuery):
        await safe_edit(query_or_message, body, markup)
    else:
        await query_or_message.answer(body, reply_markup=markup)


async def show_task(query: CallbackQuery, db: Database, task_id: str) -> None:
    await show_task_details_view(query, db, task_id)


async def run_manual_with_progress_edit(
    query: CallbackQuery,
    db: Database,
    scheduler: TaskScheduler,
    task_id: str,
) -> None:
    message = query.message
    last_text = ""

    async def progress_callback(text_msg: str) -> None:
        nonlocal last_text
        if text_msg == last_text:
            return
        last_text = text_msg
        
        back_markup = keyboards.mk([[keyboards.btn("◀️ Back to Task Details", keyboards.cb("task", "open", task_id))]])
        try:
            await message.edit_text(text_msg, reply_markup=back_markup)
        except Exception:
            pass

    try:
        await scheduler.run_task_manual(task_id, progress_callback)
    except Exception as exc:
        logger.exception("Manual run failed for task %s", task_id)
        back_markup = keyboards.mk([[keyboards.btn("◀️ Back to Task Details", keyboards.cb("task", "open", task_id))]])
        try:
            await message.edit_text(f"❌ Manual Run Failed:\n{exc}", reply_markup=back_markup)
        except Exception:
            pass


async def show_task_sources(query: CallbackQuery, db: Database, task_id: str) -> None:
    task = await db.col("tasks").find_one({"_id": ObjectId(task_id)})
    if not task:
        await query.answer("Task not found", show_alert=True)
        return
    await safe_edit(query, text.task_sources(task), keyboards.task_sources_keyboard(task))


async def show_task_destinations(query: CallbackQuery, db: Database, task_id: str) -> None:
    task = await db.col("tasks").find_one({"_id": ObjectId(task_id)})
    if not task:
        await query.answer("Task not found", show_alert=True)
        return
    await safe_edit(query, text.task_destinations(task), keyboards.task_destinations_keyboard(task))


async def show_task_source(query: CallbackQuery, db: Database, task_id: str, index: int) -> None:
    task = await db.col("tasks").find_one({"_id": ObjectId(task_id)})
    if not task or index < 0 or index >= len(task.get("sources", [])):
        await query.answer("Source not found", show_alert=True)
        return
    await safe_edit(query, text.task_source_detail(task, index), keyboards.task_source_keyboard(task, index))


async def show_task_destination(query: CallbackQuery, db: Database, task_id: str, index: int) -> None:
    task = await db.col("tasks").find_one({"_id": ObjectId(task_id)})
    if not task or index < 0 or index >= len(task.get("destinations", [])):
        await query.answer("Destination not found", show_alert=True)
        return
    await safe_edit(query, text.task_destination_detail(task, index), keyboards.task_destination_keyboard(task, index))


async def update_task_item_control(db: Database, task_id: str, index: int, action: str) -> None:
    task = await db.col("tasks").find_one({"_id": ObjectId(task_id)})
    if not task:
        return
    field = "sources" if action.startswith("src") else "destinations"
    items = list(task.get(field, []))
    if index < 0 or index >= len(items):
        return
    if action.endswith("rm"):
        items.pop(index)
    elif action.endswith("pau"):
        items[index]["status"] = "paused"
    elif action.endswith("res"):
        items[index]["status"] = "active"
    await db.col("tasks").update_one({"_id": ObjectId(task_id)}, {"$set": {field: items, "updated_at": utcnow()}})


async def safe_edit(query: CallbackQuery, body: str, markup: Any) -> None:
    try:
        await query.message.edit_text(body, reply_markup=markup)
    except Exception:
        await query.message.answer(body, reply_markup=markup)


def parse_channel_like_input(message: Message, require_numeric: bool) -> tuple[int | str, str | None, str | None]:
    forwarded = forwarded_chat(message)
    if forwarded:
        chat_id, title = forwarded
        return fix_channel_id(chat_id), title, None
    raw = (message.text or "").strip()
    if not raw:
        raise ValueError("send a chat ID, username, link, or forwarded message")
    parts = [part.strip() for part in raw.split("|")]
    value: int | str = normalize_chat_input(parts[0])
    if str(value).lstrip("-").isdigit():
        value = int(value)
    elif require_numeric:
        raise ValueError("numeric chat_id is required here, or forward a message from the channel")
    title = parts[1] if len(parts) > 1 and parts[1] else None
    link = parts[2] if len(parts) > 2 and parts[2] else None
    return fix_channel_id(value), title, link


def parse_force_input(message: Message) -> tuple[int, str | None, str | None, str]:
    value, title, link = parse_channel_like_input(message, require_numeric=True)
    raw = (message.text or "").strip()
    mode = "join"
    if raw:
        parts = [part.strip().lower() for part in raw.split("|")]
        if len(parts) > 2 and parts[2] in {"join", "request"}:
            mode = parts[2]
        if len(parts) > 3 and parts[3]:
            link = parts[3]
    return int(value), title, link, mode


def forwarded_chat(message: Message) -> tuple[int, str | None] | None:
    chat = getattr(message, "forward_from_chat", None)
    if not chat:
        origin = getattr(message, "forward_origin", None)
        chat = getattr(origin, "chat", None)
    if not chat:
        chat = getattr(message, "sender_chat", None)
    if not chat and getattr(message, "chat_shared", None):
        shared = message.chat_shared
        return int(shared.chat_id), None
    if not chat:
        return None
    return int(chat.id), getattr(chat, "title", None) or getattr(chat, "username", None)


def normalize_chat_input(raw: str) -> str:
    value = raw.strip()
    if "t.me/+" in value or "t.me/joinchat/" in value:
        return value
    if value.startswith("https://t.me/"):
        return "@" + value.removeprefix("https://t.me/").split("/", 1)[0]
    if value.startswith("http://t.me/"):
        return "@" + value.removeprefix("http://t.me/").split("/", 1)[0]
    if value.startswith("t.me/"):
        return "@" + value.removeprefix("t.me/").split("/", 1)[0]
    return value


def parse_duration_seconds(raw: str) -> int:
    value = raw.strip().lower()
    aliases = {
        "1 minute": 60,
        "5 minutes": 300,
        "10 minutes": 600,
        "20 minutes": 1200,
        "30 minutes": 1800,
        "1 hour": 3600,
    }
    if value in aliases:
        return aliases[value]
    match = re.fullmatch(r"(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)?", value)
    if not match:
        raise ValueError("use a value like 1 minute, 5m, 30m, 1 hour, or 1d")
    amount = int(match.group(1))
    unit = match.group(2) or "s"
    unit = unit[0]
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    seconds = amount * multipliers[unit]
    if seconds < 1:
        raise ValueError("duration must be positive")
    return seconds


async def add_runtime_destination(db: Database, destination: dict[str, Any]) -> None:
    runtime = await db.get_runtime_settings()
    destinations = runtime.get("destination_channels") or []
    dest_id = str(destination["chat_id"])
    if any(str(item.get("chat_id")) == dest_id for item in destinations if item.get("chat_id")):
        return
    destinations.append(
        {
            "chat_id": destination["chat_id"],
            "title": destination.get("title"),
            "link": destination.get("link"),
        }
    )
    await db.set_runtime_path("destination_channels", destinations)


def extract_telegram_id(user_doc: dict[str, Any]) -> int | None:
    for key in ("telegram_id", "user_id", "id", "_id"):
        value = user_doc.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None
