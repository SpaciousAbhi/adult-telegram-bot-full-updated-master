from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import (
    ACCESS_HOME,
    ADMIN_HOME,
    AUTO_DELETE_HOME,
    BROADCAST_HOME,
    FORCE_HOME,
    FORCE_VERIFY,
    FORWARD_TAG_TOGGLE,
    TASKS_HOME,
    USERBOT_HOME,
    cb,
)


def mk(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def admin_home_keyboard() -> InlineKeyboardMarkup:
    return mk(
        [
            [btn("🤖 Userbot Settings", USERBOT_HOME), btn("📋 Task List", TASKS_HOME)],
            [btn("⏱️ Auto Delete", AUTO_DELETE_HOME), btn("📢 Force Subscription", FORCE_HOME)],
            [btn("🔑 Access Settings", ACCESS_HOME), btn("📣 Broadcast System", BROADCAST_HOME)],
            [btn("🏷️ Forward Tag: On/Off", FORWARD_TAG_TOGGLE)],
        ]
    )


def home_back_keyboard() -> InlineKeyboardMarkup:
    return mk([[btn("◀️ Back to Admin Panel", ADMIN_HOME)]])


def userbot_keyboard(logged_in: bool) -> InlineKeyboardMarkup:
    rows = [
        [btn("📞 Login with Phone", cb("userbot", "phone")), btn("🔑 Login with String", cb("userbot", "login"))],
        [btn("🔄 Check Status", cb("userbot", "home"))],
    ]
    if logged_in:
        rows.append([btn("🚫 Logout Userbot", cb("userbot", "logout"))])
    rows.append([btn("◀️ Back to Admin Panel", ADMIN_HOME)])
    return mk(rows)


def tasks_home_keyboard(tasks: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[btn("➕ Create Task", cb("task", "new"))]]
    for task in tasks[:20]:
        rows.append([btn(task.get("name", "Task")[:40], cb("task", "open", task["_id"]))])
    rows.append([btn("◀️ Back to Admin Panel", ADMIN_HOME)])
    return mk(rows)


def task_detail_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    status = task.get("status", "draft")
    rows = [
        [btn("➕ Add Source", cb("task", "addsrc", task_id)), btn("➕ Add Destination", cb("task", "adddst", task_id))],
        [btn("📂 Manage Sources", cb("task", "srcs", task_id)), btn("📂 Manage Destinations", cb("task", "dsts", task_id))],
        [btn("📦 Storage Channel", cb("task", "storage", task_id)), btn("🗑️ Clear Storage", cb("task", "clearstorage", task_id))],
        [btn("⏱️ Set Interval", cb("task", "interval", task_id)), btn("🔢 Posts Count", cb("task", "amount", task_id))],
    ]
    if status not in {"paused", "draft"}:
        status_btn = btn("⏸️ Pause Auto-Posting", cb("task", "pause", task_id))
    else:
        status_btn = btn("▶️ Start Auto-Posting", cb("task", "resume", task_id))

    rows.append([status_btn, btn("⚡ Run Now", cb("task", "runnow", task_id))])
    rows.append([btn("🔄 Refresh", cb("task", "open", task_id)), btn("◀️ Back to Tasks List", TASKS_HOME)])
    return mk(rows)


def task_interval_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return mk(
        [
            [btn("1 minute", cb("task", "setint", task_id, 60)), btn("5 minutes", cb("task", "setint", task_id, 300))],
            [btn("10 minutes", cb("task", "setint", task_id, 600)), btn("20 minutes", cb("task", "setint", task_id, 1200))],
            [btn("30 minutes", cb("task", "setint", task_id, 1800)), btn("1 hour", cb("task", "setint", task_id, 3600))],
            [btn("◀️ Back to Task Details", cb("task", "open", task_id))],
        ]
    )


def task_amount_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return mk(
        [
            [btn("1 post", cb("task", "setamt", task_id, 1)), btn("2 posts", cb("task", "setamt", task_id, 2))],
            [btn("10 posts", cb("task", "setamt", task_id, 10)), btn("50 posts", cb("task", "setamt", task_id, 50))],
            [btn("◀️ Back to Task Details", cb("task", "open", task_id))],
        ]
    )


def task_sources_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    rows: list[list[InlineKeyboardButton]] = []
    for index, source in enumerate(task.get("sources", [])[:30]):
        label = source.get("title") or str(source.get("value"))
        rows.append([btn(f"📂 {label[:35]}", cb("task", "src", task_id, index))])
    rows.extend([[btn("➕ Add Source", cb("task", "addsrc", task_id))], [btn("◀️ Back to Task Details", cb("task", "open", task_id))]])
    return mk(rows)


def task_source_keyboard(task: dict[str, Any], index: int) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    source = task.get("sources", [])[index]
    status = source.get("status", "active")
    rows = [[btn("📝 Edit Source Link", cb("task", "srcedit", task_id, index))]]
    if status == "active":
        rows.append([btn("⏸️ Pause Scanning", cb("task", "srcpau", task_id, index))])
    else:
        rows.append([btn("▶️ Resume Scanning", cb("task", "srcres", task_id, index))])
    rows.extend([[btn("🗑️ Remove Source", cb("task", "srcrm", task_id, index))], [btn("◀️ Back to Sources", cb("task", "srcs", task_id))]])
    return mk(rows)


def task_destinations_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    rows: list[list[InlineKeyboardButton]] = []
    for index, destination in enumerate(task.get("destinations", [])[:30]):
        label = destination.get("title") or str(destination.get("chat_id"))
        rows.append([btn(f"📢 {label[:35]}", cb("task", "dst", task_id, index))])
    rows.extend([[btn("➕ Add Destination", cb("task", "adddst", task_id))], [btn("◀️ Back to Task Details", cb("task", "open", task_id))]])
    return mk(rows)


def task_destination_keyboard(task: dict[str, Any], index: int) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    destination = task.get("destinations", [])[index]
    status = destination.get("status", "active")
    rows = [[btn("📝 Edit Destination Details", cb("task", "dstedit", task_id, index))]]
    if status == "active":
        rows.append([btn("⏸️ Pause Posting", cb("task", "dstpau", task_id, index))])
    else:
        rows.append([btn("▶️ Resume Posting", cb("task", "dstres", task_id, index))])
    rows.extend(
        [[btn("🗑️ Remove Destination", cb("task", "dstrm", task_id, index))], [btn("◀️ Back to Destinations", cb("task", "dsts", task_id))]]
    )
    return mk(rows)


def force_targets_keyboard(targets: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[btn("➕ Add Force Channel", cb("force", "add"))]]
    for target in targets[:20]:
        title = target.get("title") or str(target.get("chat_id"))
        rows.append([btn(f"📢 {title[:35]}", cb("force", "target", target["chat_id"]))])
    rows.append([btn("◀️ Back to Admin Panel", ADMIN_HOME)])
    return mk(rows)


def force_target_keyboard(target: dict[str, Any]) -> InlineKeyboardMarkup:
    chat_id = int(target["chat_id"])
    mode = target.get("mode", "join")
    rows = [
        [
            btn("📢 Join Mode" + (" ✅" if mode == "join" else ""), cb("force", "mode", chat_id, "join")),
            btn("📥 Request Mode" + (" ✅" if mode == "request" else ""), cb("force", "mode", chat_id, "request")),
        ],
        [btn("🔄 Enable/Disable", cb("force", "toggle", chat_id)), btn("🔗 Refresh Invite Link", cb("force", "refresh", chat_id))],
        [btn("🗑️ Remove Channel", cb("force", "remove", chat_id))],
        [btn("◀️ Back to Channels", FORCE_HOME)],
    ]
    return mk(rows)


def force_user_keyboard(missing: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for target in missing:
        title = target.get("title") or str(target.get("chat_id"))
        label = "📥 Request Join" if target.get("mode") == "request" else "📢 Join Sponsor"
        link = target.get("invite_link")
        if link:
            rows.append([url_btn(f"{label}: {title[:25]}", link)])
    rows.append([btn("✅ Verify Access", FORCE_VERIFY)])
    rows.append([btn("👥 Referral Program", "user_referral")])
    return mk(rows)


def user_home_keyboard() -> InlineKeyboardMarkup:
    return mk([
        [btn("👥 Referral Program", "user_referral")]
    ])


def user_unjoined_destinations_keyboard(missing_dests: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for dest in missing_dests:
        title = dest.get("title") or f"Channel {dest.get('chat_id')}"
        link = dest.get("link")
        if link:
            rows.append([url_btn(f"📢 Join: {title[:25]}", link)])
    rows.append([btn("👥 Referral Program", "user_referral")])
    return mk(rows)


def delivered_file_keyboard(destinations: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [btn("👥 Referral Program", "user_referral")]
    ]
    for dest in destinations:
        title = dest.get("title") or f"Channel {dest.get('chat_id')}"
        link = dest.get("link")
        if link:
            rows.append([url_btn(f"📢 Join: {title[:25]}", link)])
    return mk(rows)


def access_keyboard() -> InlineKeyboardMarkup:
    return mk(
        [
            [btn("🔢 Set Free Limit", cb("access", "limit")), btn("💎 Grant Premium Access", cb("access", "premium"))],
            [btn("📢 Set Referral Channel", cb("access", "refchan")), btn("⚙️ Set Referral Rules", cb("access", "refrule"))],
            [btn("◀️ Back to Admin Panel", ADMIN_HOME)],
        ]
    )


def auto_delete_keyboard() -> InlineKeyboardMarkup:
    return mk(
        [
            [btn("🔄 Toggle Destination Delete", cb("autodel", "toggle", "destination")), btn("⏱️ Set Destination Time", cb("autodel", "time", "destination"))],
            [btn("🔄 Toggle Delivery Delete", cb("autodel", "toggle", "delivery")), btn("⏱️ Set Delivery Time", cb("autodel", "time", "delivery"))],
            [btn("◀️ Back to Admin Panel", ADMIN_HOME)],
        ]
    )


def broadcast_keyboard() -> InlineKeyboardMarkup:
    return mk([[btn("📣 Start Broadcast", cb("broadcast", "new"))], [btn("◀️ Back to Admin Panel", ADMIN_HOME)]])
