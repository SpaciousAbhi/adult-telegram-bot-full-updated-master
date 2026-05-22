from __future__ import annotations

from typing import Any

from app.timeutils import compact_dt, human_seconds


def yes_no(value: Any) -> str:
    return "on" if value else "off"


def admin_home(stats: dict[str, Any], runtime: dict[str, Any]) -> str:
    auto_delete = runtime.get("auto_delete") or {}
    access = runtime.get("access") or {}
    return (
        "Admin Panel\n\n"
        f"Users: {stats.get('users', 0)}\n"
        f"Tasks: {stats.get('tasks', 0)} active / {stats.get('all_tasks', 0)} total\n"
        f"Force channels: {stats.get('force_targets', 0)}\n"
        f"Stored videos: {stats.get('media', 0)}\n"
        f"Forward tag: {yes_no(runtime.get('forward_tag_enabled'))}\n"
        f"Free daily limit: {access.get('free_daily_limit', 5)}\n"
        "Auto delete: "
        f"destination {yes_no(auto_delete.get('destination_enabled'))}, "
        f"delivery {yes_no(auto_delete.get('delivery_enabled'))}"
    )


def user_home(destinations: list[dict[str, Any]]) -> str:
    if not destinations:
        return "Access ready.\n\nNo public destination channels are configured yet."
    lines = ["Access ready.", "", "Free destination channels:"]
    for item in destinations[:20]:
        title = item.get("title") or str(item.get("chat_id"))
        link = item.get("link")
        lines.append(f"- {title}" + (f": {link}" if link else ""))
    return "\n".join(lines)


def force_required(missing: list[dict[str, Any]]) -> str:
    return (
        "Complete required access first.\n\n"
        "Only unfinished channels are shown below. Join or send the request, then press Verify Access."
    )


def userbot_home(doc: dict[str, Any], configured: bool) -> str:
    logged = bool(doc.get("session_string"))
    return (
        "Userbot Management\n\n"
        f"API credentials: {yes_no(configured)}\n"
        f"Logged in: {yes_no(logged)}\n"
        f"Phone: {doc.get('phone') or 'not saved'}\n"
        f"Last error: {doc.get('last_error') or 'none'}\n\n"
        "Paste a Telethon StringSession to login. API_ID and API_HASH must be set in Heroku vars."
    )


def tasks_home(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "Task Management\n\nNo tasks yet. Create a task to start source-to-storage-to-destination posting."
    lines = ["Task Management", ""]
    for task in tasks[:20]:
        lines.append(
            f"- {task.get('name', 'Task')} | {task.get('status', 'draft')} | "
            f"{len(task.get('sources', []))} sources | {len(task.get('destinations', []))} destinations"
        )
    return "\n".join(lines)


def task_detail(task: dict[str, Any]) -> str:
    storage = task.get("storage_channel") or "not set"
    return (
        f"Task: {task.get('name')}\n\n"
        f"Status: {task.get('status', 'draft')}\n"
        f"Sources: {len(task.get('sources', []))}\n"
        f"Destinations: {len(task.get('destinations', []))}\n"
        f"Storage channel: {storage}\n"
        f"Interval: {human_seconds(int(task.get('interval_seconds') or 300))}\n"
        f"Videos per interval: {task.get('posts_per_interval', 1)}\n"
        f"Last run: {compact_dt(task.get('last_run_at'))}\n"
        f"Next run: {compact_dt(task.get('next_run_at'))}\n"
        f"Last result: {task.get('last_error') or 'ok'}"
    )


def task_sources(task: dict[str, Any]) -> str:
    sources = task.get("sources", [])
    if not sources:
        return f"Task Sources: {task.get('name')}\n\nNo sources added."
    lines = [f"Task Sources: {task.get('name')}", ""]
    for index, source in enumerate(sources, start=1):
        lines.append(f"{index}. {source.get('title') or source.get('value')} | {source.get('status', 'active')}")
    return "\n".join(lines)


def task_source_detail(task: dict[str, Any], index: int) -> str:
    source = task.get("sources", [])[index]
    return (
        f"Source {index + 1}: {task.get('name')}\n\n"
        f"Title: {source.get('title') or source.get('value')}\n"
        f"Value: {source.get('value')}\n"
        f"Status: {source.get('status', 'active')}\n"
        f"Last message: {source.get('last_message_id') or 'not scanned'}"
    )


def task_destinations(task: dict[str, Any]) -> str:
    destinations = task.get("destinations", [])
    if not destinations:
        return f"Task Destinations: {task.get('name')}\n\nNo destinations added."
    lines = [f"Task Destinations: {task.get('name')}", ""]
    for index, destination in enumerate(destinations, start=1):
        lines.append(
            f"{index}. {destination.get('title') or destination.get('chat_id')} | "
            f"{destination.get('status', 'active')}"
        )
    return "\n".join(lines)


def task_destination_detail(task: dict[str, Any], index: int) -> str:
    destination = task.get("destinations", [])[index]
    return (
        f"Destination {index + 1}: {task.get('name')}\n\n"
        f"Title: {destination.get('title') or destination.get('chat_id')}\n"
        f"Chat ID: {destination.get('chat_id')}\n"
        f"Link: {destination.get('link') or 'not set'}\n"
        f"Status: {destination.get('status', 'active')}"
    )


def force_home(targets: list[dict[str, Any]]) -> str:
    if not targets:
        return "Advanced Force Subscription\n\nNo required channels are configured."
    lines = ["Advanced Force Subscription", ""]
    for target in targets[:30]:
        title = target.get("title") or str(target.get("chat_id"))
        lines.append(
            f"- {title} | {target.get('mode', 'join')} | {yes_no(target.get('enabled', True))}"
        )
    return "\n".join(lines)


def access_home(runtime: dict[str, Any]) -> str:
    access = runtime.get("access") or {}
    referral = runtime.get("referral") or {}
    return (
        "User Access Settings\n\n"
        f"Free daily limit: {access.get('free_daily_limit', 5)}\n"
        f"Premium methods: {', '.join(access.get('premium_methods') or [])}\n"
        f"Referral channel: {referral.get('channel_id') or 'not set'}\n"
        f"Referral requirement: {referral.get('required_joins', 10)} joins\n"
        f"Referral reward: {referral.get('reward_limit', 100)} per day for "
        f"{referral.get('reward_days', 5)} days"
    )


def auto_delete_home(runtime: dict[str, Any]) -> str:
    settings = runtime.get("auto_delete") or {}
    return (
        "Auto Delete Settings\n\n"
        f"Destination posts: {yes_no(settings.get('destination_enabled'))} "
        f"after {human_seconds(settings.get('destination_seconds'))}\n"
        f"User-delivered videos: {yes_no(settings.get('delivery_enabled'))} "
        f"after {human_seconds(settings.get('delivery_seconds'))}"
    )


def broadcast_home(stats: dict[str, Any]) -> str:
    return (
        "Advanced Broadcasting System\n\n"
        f"Saved users: {stats.get('users', 0)}\n"
        f"Broadcasts created: {stats.get('broadcasts', 0)}\n\n"
        "Start a broadcast, then send or forward the message to copy to saved users."
    )
