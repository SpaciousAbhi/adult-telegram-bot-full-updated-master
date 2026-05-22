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
            [btn("Userbot Management", USERBOT_HOME)],
            [btn("Task Management", TASKS_HOME)],
            [btn("Forward Tag On / Off", FORWARD_TAG_TOGGLE)],
            [btn("Auto Delete Settings", AUTO_DELETE_HOME)],
            [btn("Advanced Force Subscription", FORCE_HOME)],
            [btn("User Access Settings", ACCESS_HOME)],
            [btn("Advanced Broadcasting System", BROADCAST_HOME)],
        ]
    )


def home_back_keyboard() -> InlineKeyboardMarkup:
    return mk([[btn("Back", ADMIN_HOME)]])


def userbot_keyboard(logged_in: bool) -> InlineKeyboardMarkup:
    rows = [
        [btn("Login With Phone Code", cb("userbot", "phone"))],
        [btn("Login With StringSession", cb("userbot", "login"))],
        [btn("Check Status", cb("userbot", "home"))],
    ]
    if logged_in:
        rows.append([btn("Logout Userbot", cb("userbot", "logout"))])
    rows.append([btn("Back", ADMIN_HOME)])
    return mk(rows)


def tasks_home_keyboard(tasks: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[btn("Create Task", cb("task", "new"))]]
    for task in tasks[:20]:
        rows.append([btn(task.get("name", "Task")[:40], cb("task", "open", task["_id"]))])
    rows.append([btn("Back", ADMIN_HOME)])
    return mk(rows)


def task_detail_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    status = task.get("status", "draft")
    rows = [
        [btn("Add Source", cb("task", "addsrc", task_id)), btn("Add Destination", cb("task", "adddst", task_id))],
        [btn("Manage Sources", cb("task", "srcs", task_id)), btn("Manage Destinations", cb("task", "dsts", task_id))],
        [btn("Set Storage Channel", cb("task", "storage", task_id)), btn("Remove Storage", cb("task", "clearstorage", task_id))],
        [btn("Set Interval", cb("task", "interval", task_id)), btn("Set Amount", cb("task", "amount", task_id))],
    ]
    if status == "active":
        rows.append([btn("Pause Task", cb("task", "pause", task_id)), btn("Stop Task", cb("task", "stop", task_id))])
    elif status == "paused":
        rows.append([btn("Resume Task", cb("task", "resume", task_id)), btn("Stop Task", cb("task", "stop", task_id))])
    else:
        rows.append([btn("Start Task", cb("task", "resume", task_id)), btn("Stop Task", cb("task", "stop", task_id))])
    rows.extend([[btn("Refresh", cb("task", "open", task_id))], [btn("Back", TASKS_HOME)]])
    return mk(rows)


def task_sources_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    rows: list[list[InlineKeyboardButton]] = []
    for index, source in enumerate(task.get("sources", [])[:30]):
        label = source.get("title") or str(source.get("value"))
        rows.append([btn(label[:40], cb("task", "src", task_id, index))])
    rows.extend([[btn("Add Source", cb("task", "addsrc", task_id))], [btn("Back", cb("task", "open", task_id))]])
    return mk(rows)


def task_source_keyboard(task: dict[str, Any], index: int) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    source = task.get("sources", [])[index]
    status = source.get("status", "active")
    rows = [[btn("Edit Source", cb("task", "srcedit", task_id, index))]]
    if status == "active":
        rows.append([btn("Pause Source", cb("task", "srcpau", task_id, index))])
    else:
        rows.append([btn("Resume Source", cb("task", "srcres", task_id, index))])
    rows.extend([[btn("Remove Source", cb("task", "srcrm", task_id, index))], [btn("Back", cb("task", "srcs", task_id))]])
    return mk(rows)


def task_destinations_keyboard(task: dict[str, Any]) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    rows: list[list[InlineKeyboardButton]] = []
    for index, destination in enumerate(task.get("destinations", [])[:30]):
        label = destination.get("title") or str(destination.get("chat_id"))
        rows.append([btn(label[:40], cb("task", "dst", task_id, index))])
    rows.extend([[btn("Add Destination", cb("task", "adddst", task_id))], [btn("Back", cb("task", "open", task_id))]])
    return mk(rows)


def task_destination_keyboard(task: dict[str, Any], index: int) -> InlineKeyboardMarkup:
    task_id = str(task["_id"])
    destination = task.get("destinations", [])[index]
    status = destination.get("status", "active")
    rows = [[btn("Edit Destination", cb("task", "dstedit", task_id, index))]]
    if status == "active":
        rows.append([btn("Pause Destination", cb("task", "dstpau", task_id, index))])
    else:
        rows.append([btn("Resume Destination", cb("task", "dstres", task_id, index))])
    rows.extend(
        [[btn("Remove Destination", cb("task", "dstrm", task_id, index))], [btn("Back", cb("task", "dsts", task_id))]]
    )
    return mk(rows)


def force_targets_keyboard(targets: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[btn("Add Force Channel", cb("force", "add"))]]
    for target in targets[:20]:
        title = target.get("title") or str(target.get("chat_id"))
        rows.append([btn(title[:35], cb("force", "target", target["chat_id"]))])
    rows.append([btn("Back", ADMIN_HOME)])
    return mk(rows)


def force_target_keyboard(target: dict[str, Any]) -> InlineKeyboardMarkup:
    chat_id = int(target["chat_id"])
    mode = target.get("mode", "join")
    rows = [
        [
            btn("Join Mode" + (" On" if mode == "join" else ""), cb("force", "mode", chat_id, "join")),
            btn("Request Mode" + (" On" if mode == "request" else ""), cb("force", "mode", chat_id, "request")),
        ],
        [btn("On / Off", cb("force", "toggle", chat_id)), btn("Refresh Link", cb("force", "refresh", chat_id))],
        [btn("Remove", cb("force", "remove", chat_id))],
        [btn("Back", FORCE_HOME)],
    ]
    return mk(rows)


def force_user_keyboard(missing: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for target in missing:
        title = target.get("title") or str(target.get("chat_id"))
        label = "Send Request" if target.get("mode") == "request" else "Join Channel"
        link = target.get("invite_link")
        if link:
            rows.append([url_btn(f"{label}: {title[:28]}", link)])
    rows.append([btn("Verify Access", FORCE_VERIFY)])
    return mk(rows)


def access_keyboard() -> InlineKeyboardMarkup:
    return mk(
        [
            [btn("Set Free Limit", cb("access", "limit"))],
            [btn("Grant Premium", cb("access", "premium"))],
            [btn("Set Referral Channel", cb("access", "refchan"))],
            [btn("Set Referral Rule", cb("access", "refrule"))],
            [btn("Back", ADMIN_HOME)],
        ]
    )


def auto_delete_keyboard() -> InlineKeyboardMarkup:
    return mk(
        [
            [btn("Toggle Destination Delete", cb("autodel", "toggle", "destination"))],
            [btn("Set Destination Time", cb("autodel", "time", "destination"))],
            [btn("Toggle Delivery Delete", cb("autodel", "toggle", "delivery"))],
            [btn("Set Delivery Time", cb("autodel", "time", "delivery"))],
            [btn("Back", ADMIN_HOME)],
        ]
    )


def broadcast_keyboard() -> InlineKeyboardMarkup:
    return mk([[btn("Start Broadcast", cb("broadcast", "new"))], [btn("Back", ADMIN_HOME)]])
