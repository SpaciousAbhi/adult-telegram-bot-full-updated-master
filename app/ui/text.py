from __future__ import annotations

from html import escape
from typing import Any

from app.timeutils import compact_dt, human_seconds


DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def _safe(value: Any, fallback: str = "None") -> str:
    if value is None or value == "":
        return fallback
    return escape(str(value), quote=False)


def _code(value: Any, fallback: str = "None") -> str:
    return f"<code>{_safe(value, fallback)}</code>"


def _short(value: Any, limit: int = 140, fallback: str = "None") -> str:
    text = str(value if value is not None and value != "" else fallback)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _secret(value: Any) -> str:
    if not value:
        return "Not set"
    raw = str(value)
    if len(raw) <= 8:
        return "Configured"
    return f"{escape(raw[:4], quote=False)}…{escape(raw[-4:], quote=False)}"


def yes_no(value: Any) -> str:
    return "🟢 On" if value else "🔴 Off"


def _status_badge(status: str) -> str:
    return {
        "active": "🟢 Active",
        "paused": "⏸ Paused",
        "draft": "📝 Draft",
        "cooldown": "🟡 Cooling down",
        "error": "🔴 Error",
    }.get(status, f"⚪ {_safe(status).title()}")


def admin_home(stats: dict[str, Any], runtime: dict[str, Any]) -> str:
    auto_delete = runtime.get("auto_delete") or {}
    access = runtime.get("access") or {}
    forward_tag = yes_no(runtime.get("forward_tag_enabled"))
    dest_del = yes_no(auto_delete.get("destination_enabled"))
    delivery_del = yes_no(auto_delete.get("delivery_enabled"))
    return (
        "🛠 <b>Admin Command Center</b>\n"
        f"{DIVIDER}\n"
        "Live control for posting, access, delivery, and monetization.\n\n"
        "📊 <b>System Snapshot</b>\n"
        f"• Users: {_code(stats.get('users', 0))}\n"
        f"• Active tasks: {_code(stats.get('tasks', 0))} / {_code(stats.get('all_tasks', 0))}\n"
        f"• Force-sub channels: {_code(stats.get('force_targets', 0))}\n"
        f"• Stored videos: {_code(stats.get('media', 0))}\n\n"
        "⚙️ <b>Runtime Status</b>\n"
        f"• Forward author tag: <b>{forward_tag}</b>\n"
        f"• Free daily limit: {_code(access.get('free_daily_limit', 5))} downloads\n"
        f"• Destination auto-delete: <b>{dest_del}</b>\n"
        f"• Delivery auto-delete: <b>{delivery_del}</b>\n"
        f"{DIVIDER}\n"
        "<i>Choose a section below. Routine controls are grouped away from risky actions.</i>"
    )


def user_home(destinations: list[dict[str, Any]]) -> str:
    if not destinations:
        return (
            "✨ <b>Premium Hub</b>\n"
            f"{DIVIDER}\n"
            "Your access panel is ready.\n\n"
            "No public destination channels are configured yet, so new video drops are not visible here right now.\n\n"
            "👥 Use the referral option below if you want to unlock a higher daily limit once the channel is active."
        )

    lines = [
        "✨ <b>Premium Hub</b>",
        DIVIDER,
        "Your access panel is ready. Open the channels below for new drops, updates, and direct video access.",
        "",
        "📢 <b>Content Channels</b>",
    ]
    for item in destinations[:20]:
        title = item.get("title") or str(item.get("chat_id"))
        link = item.get("link")
        if link:
            lines.append(f"• <a href=\"{escape(str(link), quote=True)}\">{_safe(title)}</a>")
        else:
            lines.append(f"• <b>{_safe(title)}</b>")
    lines.extend(
        [
            "",
            "👥 <b>Want more daily access?</b>",
            "Open the referral program and invite friends to earn premium limits.",
            DIVIDER,
        ]
    )
    return "\n".join(lines)


def force_required(missing: list[dict[str, Any]]) -> str:
    count = len(missing)
    channel_word = "channel" if count == 1 else "channels"
    return (
        "🔐 <b>Access Check Required</b>\n"
        f"{DIVIDER}\n"
        f"Join or request access to the {count} required {channel_word} below before unlocking this content.\n\n"
        "1. Open each required channel.\n"
        "2. Join, or send the join request when Telegram asks.\n"
        "3. Return here and tap <b>Verify Access</b>.\n\n"
        "<i>Only unfinished channels are shown, so this screen stays short.</i>"
    )


def userbot_home(doc: dict[str, Any], configured: bool) -> str:
    logged = bool(doc.get("session_string"))
    cred_status = "🟢 Configured" if configured else "🔴 Missing"
    login_status = "🟢 Logged in" if logged else "🔴 Logged out"
    phone_str = doc.get("phone") or "Not set"
    err_str = _short(doc.get("last_error"), 160, "No recent error")
    return (
        "🤖 <b>Userbot Control</b>\n"
        f"{DIVIDER}\n"
        "The userbot scans source channels and moves videos into storage for posting.\n\n"
        f"• API credentials: <b>{cred_status}</b>\n"
        f"• Login status: <b>{login_status}</b>\n"
        f"• Phone: {_code(phone_str)}\n"
        f"• Last error: {_code(err_str, 'No recent error')}\n\n"
        "🔁 <b>Login Flow</b>\n"
        "API ID → API Hash → Phone or StringSession → Code → 2FA if enabled\n"
        f"{DIVIDER}"
    )


def tasks_home(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return (
            "📋 <b>Posting Tasks</b>\n"
            f"{DIVIDER}\n"
            "No posting task exists yet.\n\n"
            "Create one task, add source channels, set a storage channel, then connect destinations. The scheduler will handle collection and posting after the task is started."
        )

    lines = [
        "📋 <b>Posting Tasks</b>",
        DIVIDER,
        "Select a task to inspect health, timing, sources, destinations, and manual controls.",
        "",
    ]
    for task in tasks[:20]:
        status = str(task.get("status", "draft"))
        name = _safe(task.get("name", "Task"))
        sources_count = len(task.get("sources", []))
        dest_count = len(task.get("destinations", []))
        lines.append(
            f"{_status_badge(status)} · <b>{name}</b>\n"
            f"   {sources_count} sources → {dest_count} destinations"
        )
    lines.append(DIVIDER)
    return "\n".join(lines)


def task_detail(task: dict[str, Any], pending_count: int, last_posted_token: str | None) -> str:
    status = str(task.get("status", "draft"))
    interval_seconds = int(task.get("interval_seconds") or 300)
    last_error = task.get("last_error") or "No recent issue"
    return (
        f"📋 <b>Task: {_safe(task.get('name'), 'Task')}</b>\n"
        f"{DIVIDER}\n"
        f"• Status: <b>{_status_badge(status)}</b>\n"
        f"• Storage channel: {_code(task.get('storage_channel'), 'Not set')}\n"
        f"• Sources: {_code(len(task.get('sources', [])))} active\n"
        f"• Destinations: {_code(len(task.get('destinations', [])))} active\n"
        f"• Pending Videos (in storage): {_code(pending_count)}\n\n"
        "⏱ <b>Schedule</b>\n"
        f"• Interval: {_code(human_seconds(interval_seconds))}\n"
        f"• Batch size: {_code(task.get('posts_per_interval', 1))} video(s)\n"
        f"• Last run: {_code(compact_dt(task.get('last_run_at')))}\n"
        f"• Next post: {_code(compact_dt(task.get('next_run_at')))}\n"
        f"• Next source scan: {_code(compact_dt(task.get('next_collect_at')))}\n\n"
        "📈 <b>Latest Result</b>\n"
        f"• Saved last run: {_code(task.get('last_saved_count', 0))}\n"
        f"• Posted last run: {_code(task.get('last_post_count', 0))}\n"
        f"• Last posted token: {_code(last_posted_token, 'None')}\n"
        f"• Last result: {_code(_short(last_error, 180, 'No recent issue'))}\n"
        f"{DIVIDER}"
    )


def task_sources(task: dict[str, Any]) -> str:
    sources = task.get("sources", [])
    if not sources:
        return (
            f"📥 <b>Sources: {_safe(task.get('name'), 'Task')}</b>\n"
            f"{DIVIDER}\n"
            "No sources added yet. Add at least one source channel before starting collection."
        )

    lines = [f"📥 <b>Sources: {_safe(task.get('name'), 'Task')}</b>", DIVIDER]
    for index, source in enumerate(sources, start=1):
        status = _status_badge(str(source.get("status", "active")))
        title = source.get("title") or "No title"
        lines.append(
            f"{index}. <b>{status}</b>\n"
            f"   {_code(source.get('value'))} · {_safe(title)}"
        )
    lines.append(DIVIDER)
    return "\n".join(lines)


def task_source_detail(task: dict[str, Any], index: int) -> str:
    source = task.get("sources", [])[index]
    status = _status_badge(str(source.get("status", "active")))
    return (
        f"📥 <b>Source #{index + 1}</b>\n"
        f"{DIVIDER}\n"
        f"• Task: <b>{_safe(task.get('name'), 'Task')}</b>\n"
        f"• Title: {_code(source.get('title'), 'No title')}\n"
        f"• Link / ID: {_code(source.get('value'))}\n"
        f"• Status: <b>{status}</b>\n"
        f"• Last message ID: {_code(source.get('last_message_id'), 'Not scanned')}\n"
        f"{DIVIDER}"
    )


def task_destinations(task: dict[str, Any]) -> str:
    destinations = task.get("destinations", [])
    if not destinations:
        return (
            f"📤 <b>Destinations: {_safe(task.get('name'), 'Task')}</b>\n"
            f"{DIVIDER}\n"
            "No destinations added yet. Add at least one destination channel before posting."
        )

    lines = [f"📤 <b>Destinations: {_safe(task.get('name'), 'Task')}</b>", DIVIDER]
    for index, destination in enumerate(destinations, start=1):
        status = _status_badge(str(destination.get("status", "active")))
        title = destination.get("title") or destination.get("chat_id")
        lines.append(f"{index}. <b>{status}</b> · {_safe(title)}")
    lines.append(DIVIDER)
    return "\n".join(lines)


def task_destination_detail(task: dict[str, Any], index: int) -> str:
    destination = task.get("destinations", [])[index]
    status = _status_badge(str(destination.get("status", "active")))
    return (
        f"📤 <b>Destination #{index + 1}</b>\n"
        f"{DIVIDER}\n"
        f"• Task: <b>{_safe(task.get('name'), 'Task')}</b>\n"
        f"• Title: {_code(destination.get('title'), 'No title')}\n"
        f"• Chat ID: {_code(destination.get('chat_id'))}\n"
        f"• Public link: {_code(destination.get('link'), 'Not set')}\n"
        f"• Status: <b>{status}</b>\n"
        f"{DIVIDER}"
    )


def force_home(targets: list[dict[str, Any]]) -> str:
    if not targets:
        return (
            "🔐 <b>Force Subscription</b>\n"
            f"{DIVIDER}\n"
            "No required channels are configured.\n\n"
            "Add channels here when users must join or request access before opening videos."
        )

    lines = [
        "🔐 <b>Force Subscription</b>",
        DIVIDER,
        "Users must clear these access checks before protected content opens.",
        "",
    ]
    for target in targets[:30]:
        title = target.get("title") or str(target.get("chat_id"))
        mode = "Request" if target.get("mode") == "request" else "Join"
        status = "🟢 Enabled" if target.get("enabled", True) else "🔴 Disabled"
        lines.append(f"• <b>{_safe(title)}</b>\n   Mode: {_code(mode)} · {status}")
    lines.append(DIVIDER)
    return "\n".join(lines)


def access_home(runtime: dict[str, Any]) -> str:
    access = runtime.get("access") or {}
    referral = runtime.get("referral") or {}
    premium_methods = ", ".join(access.get("premium_methods") or []) or "Not set"
    ref_channel = referral.get("channel_id") or "Not set"
    return (
        "💎 <b>Access & Premium</b>\n"
        f"{DIVIDER}\n"
        "Control free limits, premium grants, and referral rewards from one place.\n\n"
        "📦 <b>Daily Limits</b>\n"
        f"• Free users: {_code(access.get('free_daily_limit', 5))} downloads\n"
        f"• Premium users: {_code(access.get('premium_daily_limit') or 'No limit')}\n"
        f"• Payment methods: {_code(premium_methods)}\n\n"
        "👥 <b>Referral Rewards</b>\n"
        f"• Sponsor channel: {_code(ref_channel)}\n"
        f"• Required joins: {_code(referral.get('required_joins', 10))}\n"
        f"• Reward duration: {_code(referral.get('reward_days', 5))} days\n"
        f"• Reward limit: {_code(referral.get('reward_limit', 100))} downloads/day\n"
        f"{DIVIDER}"
    )


def auto_delete_home(runtime: dict[str, Any]) -> str:
    settings = runtime.get("auto_delete") or {}
    dest_enabled = yes_no(settings.get("destination_enabled"))
    deliv_enabled = yes_no(settings.get("delivery_enabled"))
    return (
        "⏱ <b>Auto-Delete</b>\n"
        f"{DIVIDER}\n"
        "Keep public channels and user chats clean by deleting selected bot messages after a delay.\n\n"
        "📤 <b>Destination Posts</b>\n"
        f"• Status: <b>{dest_enabled}</b>\n"
        f"• Delay: {_code(human_seconds(settings.get('destination_seconds')))}\n\n"
        "🎬 <b>User Deliveries</b>\n"
        f"• Status: <b>{deliv_enabled}</b>\n"
        f"• Delay: {_code(human_seconds(settings.get('delivery_seconds')))}\n"
        f"{DIVIDER}"
    )


def broadcast_home(stats: dict[str, Any]) -> str:
    return (
        "📣 <b>Broadcast Center</b>\n"
        f"{DIVIDER}\n"
        "Send one prepared message to every saved user. The bot will clone the message and update progress while it runs.\n\n"
        f"• Audience: {_code(stats.get('users', 0))} users\n"
        f"• Previous broadcasts: {_code(stats.get('broadcasts', 0))}\n\n"
        "1. Tap <b>Start Broadcast</b>.\n"
        "2. Send or forward the exact message to broadcast.\n"
        "3. Watch the progress message until it finishes.\n"
        f"{DIVIDER}"
    )


def diskwala_settings(runtime: dict[str, Any]) -> str:
    diskwala = runtime.get("diskwala", {})
    enabled = yes_no(diskwala.get("enabled"))
    bot_username = diskwala.get("bot_username") or "Not set"
    return (
        "🔗 <b>Diskwala Delivery</b>\n"
        f"{DIVIDER}\n"
        "When enabled, stored videos with Diskwala links are delivered as a secure external link instead of a copied file.\n\n"
        f"• Status: <b>{enabled}</b>\n"
        f"• API key: {_code(_secret(diskwala.get('api_key')))}\n"
        f"• Uploader bot: {_code(bot_username)}\n\n"
        "Requirements: userbot logged in, uploader bot reachable, and Diskwala API key configured.\n"
        f"{DIVIDER}"
    )
