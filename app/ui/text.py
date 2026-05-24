from __future__ import annotations

from typing import Any

from app.timeutils import compact_dt, human_seconds


def yes_no(value: Any) -> str:
    return "🟢 on" if value else "🔴 off"


def admin_home(stats: dict[str, Any], runtime: dict[str, Any]) -> str:
    auto_delete = runtime.get("auto_delete") or {}
    access = runtime.get("access") or {}
    forward_tag = "🟢 Enabled" if runtime.get('forward_tag_enabled') else "🔴 Disabled"
    dest_del = "🟢 Active" if auto_delete.get('destination_enabled') else "🔴 Inactive"
    delivery_del = "🟢 Active" if auto_delete.get('delivery_enabled') else "🔴 Inactive"
    return (
        "🛠️ <b>ADMIN DASHBOARD</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "📊 <b>System Overview:</b>\n"
        f"• 👥 <b>Total Users:</b> <code>{stats.get('users', 0)}</code>\n"
        f"• 📋 <b>Posting Tasks:</b> <code>{stats.get('tasks', 0)}</code> active / <code>{stats.get('all_tasks', 0)}</code> total\n"
        f"• 📢 <b>Force-Sub Channels:</b> <code>{stats.get('force_targets', 0)}</code> channels\n"
        f"• 📦 <b>Stored Media Items:</b> <code>{stats.get('media', 0)}</code> videos\n\n"
        "⚙️ <b>Runtime Settings:</b>\n"
        f"• ➡️ <b>Forward Author Tag:</b> {forward_tag}\n"
        f"• 🔑 <b>Free Daily Limit:</b> <code>{access.get('free_daily_limit', 5)}</code> downloads\n"
        f"• ⏱️ <b>Auto Delete Destination:</b> {dest_del}\n"
        f"• ⏱️ <b>Auto Delete Delivery:</b> {delivery_del}\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "<i>Select an option below to configure the system:</i>"
    )


def user_home(destinations: list[dict[str, Any]]) -> str:
    if not destinations:
        return (
            "✨ <b>Welcome!</b> 👋\n\n"
            "Your access is ready. No destination channels are configured yet, "
            "so videos are not available from the public channel list right now."
        )
    lines = [
        "✨ <b>Access Ready!</b> 👋\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "Join our channels below to get direct access to premium videos and daily updates:\n"
    ]
    for item in destinations[:20]:
        title = item.get("title") or str(item.get("chat_id"))
        link = item.get("link")
        if link:
            lines.append(f"• 📢 <a href=\"{link}\">{title}</a>")
        else:
            lines.append(f"• 📢 <b>{title}</b>")
    lines.append("\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    lines.append("<i>Need more limit? Use the referral program to earn free premium access!</i>")
    return "\n".join(lines)


def force_required(missing: list[dict[str, Any]]) -> str:
    return (
        "⚠️ <b>Access Restricted</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "To view this content, you must join our partner channels first.\n\n"
        "<b>Instructions:</b>\n"
        "1. Click each channel button below and join/request access.\n"
        "2. Once joined, tap <b>Verify Access</b> below to unlock your content.\n\n"
        "<i>Note: Only unfinished channels are shown below.</i>"
    )


def userbot_home(doc: dict[str, Any], configured: bool) -> str:
    logged = bool(doc.get("session_string"))
    cred_status = "✅ Configured" if configured else "❌ Not configured"
    login_status = "✅ Logged In" if logged else "❌ Logged Out"
    phone_str = doc.get('phone') or "None"
    err_str = doc.get('last_error') or "None"
    return (
        "🤖 <b>USERBOT MANAGEMENT</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "Use the userbot to automatically harvest content from your source channels.\n\n"
        f"• 🔑 <b>API Credentials:</b> {cred_status}\n"
        f"• 👤 <b>Login Status:</b> {login_status}\n"
        f"• 📞 <b>Phone Number:</b> <code>{phone_str}</code>\n"
        f"• ⚠️ <b>Last Error:</b> <code>{err_str}</code>\n\n"
        "<b>Standard Login Flow:</b>\n"
        "API ID ➜ API Hash ➜ Phone Number ➜ Login Code ➜ 2FA Password\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )


def tasks_home(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return (
            "📋 <b>TASK MANAGEMENT</b>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "No tasks configured yet. Create a task to start source-to-storage-to-destination posting."
        )
    lines = [
        "📋 <b>TASK MANAGEMENT</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "<i>Select a task below to manage its posting flow:</i>\n"
    ]
    for task in tasks[:20]:
        status = task.get("status", "draft")
        status_emoji = {
            "active": "🟢",
            "paused": "⏸️",
            "draft": "📝",
            "cooldown": "❄️",
            "error": "🔴",
        }.get(status, "⚪")
        name = task.get("name", "Task")
        sources_count = len(task.get("sources", []))
        dest_count = len(task.get("destinations", []))
        lines.append(
            f"{status_emoji} <b>{name}</b> (<code>{status}</code>)\n"
            f"   • {sources_count} sources ➜ {dest_count} destinations"
        )
    lines.append("\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    return "\n".join(lines)


def task_detail(task: dict[str, Any], pending_count: int, last_posted_token: str | None) -> str:
    storage = task.get("storage_channel") or "Not Set"
    last_posted = last_posted_token or "None"
    status = task.get("status", "draft")
    status_emoji = {
        "active": "🟢",
        "paused": "⏸️",
        "draft": "📝",
        "cooldown": "❄️",
        "error": "🔴",
    }.get(status, "⚪")
    
    interval_seconds = int(task.get("interval_seconds") or 300)
    interval_text = human_seconds(interval_seconds)
    
    last_error = task.get("last_error") or "None"
    
    return (
        f"📋 <b>Task: {task.get('name')}</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"• <b>Status:</b> {status_emoji} <code>{status}</code>\n"
        f"• 📦 <b>Storage Channel:</b> <code>{storage}</code>\n"
        f"• ⏱️ <b>Post Interval:</b> <code>{interval_text}</code>\n"
        f"• 🔢 <b>Posts Per Interval:</b> <code>{task.get('posts_per_interval', 1)}</code> video(s)\n"
        f"• 📂 <b>Sources:</b> <code>{len(task.get('sources', []))}</code> active\n"
        f"• 📢 <b>Destinations:</b> <code>{len(task.get('destinations', []))}</code> active\n"
        f"• ⏳ <b>Pending Videos (in storage): <code>{pending_count}</code></b>\n\n"
        "📊 <b>Execution Details:</b>\n"
        f"• ⏳ <b>Last Run:</b> <code>{compact_dt(task.get('last_run_at'))}</code>\n"
        f"• ⏳ <b>Next Run:</b> <code>{compact_dt(task.get('next_run_at'))}</code>\n"
        f"• 🔍 <b>Next Source Scan:</b> <code>{compact_dt(task.get('next_collect_at'))}</code>\n"
        f"• 📥 <b>Last Saved Count:</b> <code>{task.get('last_saved_count', 0)}</code>\n"
        f"• 📤 <b>Last Posted Count:</b> <code>{task.get('last_post_count', 0)}</code>\n"
        f"• 🔗 <b>Last posted token: <code>{last_posted}</code></b>\n"
        f"• ⚠️ <b>Last result: <code>{last_error}</code></b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )


def task_sources(task: dict[str, Any]) -> str:
    sources = task.get("sources", [])
    if not sources:
        return f"📂 <b>Sources: {task.get('name')}</b>\n\nNo sources added."
    lines = [f"📂 <b>Sources: {task.get('name')}</b>", "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]
    for index, source in enumerate(sources, start=1):
        status = source.get("status", "active")
        status_emoji = "🟢" if status == "active" else "⏸️"
        lines.append(f"{index}. {status_emoji} <code>{source.get('value')}</code> ({source.get('title') or 'no title'})")
    lines.append("▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    return "\n".join(lines)


def task_source_detail(task: dict[str, Any], index: int) -> str:
    source = task.get("sources", [])[index]
    status = source.get("status", "active")
    status_emoji = "🟢" if status == "active" else "⏸️"
    return (
        f"🔍 <b>SOURCE #{index + 1} DETAILS</b>\n"
        f"Task: <b>{task.get('name')}</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"• 👤 <b>Custom Title:</b> <code>{source.get('title') or 'None'}</code>\n"
        f"• 🔗 <b>Value / Chat Link:</b> <code>{source.get('value')}</code>\n"
        f"• 📊 <b>Status:</b> {status_emoji} <code>{status}</code>\n"
        f"• 📑 <b>Last Message ID:</b> <code>{source.get('last_message_id') or 'Not scanned'}</code>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )


def task_destinations(task: dict[str, Any]) -> str:
    destinations = task.get("destinations", [])
    if not destinations:
        return f"📢 <b>Destinations: {task.get('name')}</b>\n\nNo destinations added."
    lines = [f"📢 <b>Destinations: {task.get('name')}</b>", "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]
    for index, destination in enumerate(destinations, start=1):
        status = destination.get("status", "active")
        status_emoji = "🟢" if status == "active" else "⏸️"
        lines.append(f"{index}. {status_emoji} <b>{destination.get('title') or destination.get('chat_id')}</b>")
    lines.append("▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    return "\n".join(lines)


def task_destination_detail(task: dict[str, Any], index: int) -> str:
    destination = task.get("destinations", [])[index]
    status = destination.get("status", "active")
    status_emoji = "🟢" if status == "active" else "⏸️"
    return (
        f"🔍 <b>DESTINATION #{index + 1} DETAILS</b>\n"
        f"Task: <b>{task.get('name')}</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"• 🏷️ <b>Title:</b> <code>{destination.get('title') or 'None'}</code>\n"
        f"• 🆔 <b>Chat ID:</b> <code>{destination.get('chat_id')}</code>\n"
        f"• 🔗 <b>Invite/Public Link:</b> <code>{destination.get('link') or 'Not set'}</code>\n"
        f"• 📊 <b>Status:</b> {status_emoji} <code>{status}</code>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )


def force_home(targets: list[dict[str, Any]]) -> str:
    if not targets:
        return (
            "📢 <b>ADVANCED FORCE SUBSCRIPTION</b>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "No required force subscription channels configured."
        )
    lines = [
        "📢 <b>ADVANCED FORCE SUBSCRIPTION</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "<i>Users must join these channels to unlock videos:</i>\n"
    ]
    for target in targets[:30]:
        title = target.get("title") or str(target.get("chat_id"))
        mode = target.get("mode", "join")
        mode_text = "📥 Request Mode" if mode == "request" else "📢 Join Mode"
        status_text = "🟢 Enabled" if target.get("enabled", True) else "🔴 Disabled"
        lines.append(f"• <b>{title}</b>\n   ({mode_text} | {status_text})")
    lines.append("\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    return "\n".join(lines)


def access_home(runtime: dict[str, Any]) -> str:
    access = runtime.get("access") or {}
    referral = runtime.get("referral") or {}
    premium_methods = ", ".join(access.get("premium_methods") or []) or "None"
    ref_channel = referral.get("channel_id") or "Not set"
    return (
        "🔑 <b>USER ACCESS SETTINGS</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "📦 <b>Daily Limits:</b>\n"
        f"• Free Daily Limit: <code>{access.get('free_daily_limit', 5)}</code> downloads\n"
        f"• Premium Daily Limit: <code>{access.get('premium_daily_limit') or 'No Limit'}</code>\n"
        f"• Payment Methods: <code>{premium_methods}</code>\n\n"
        "👥 <b>Referral System:</b>\n"
        f"• Referral Sponsor Channel: <code>{ref_channel}</code>\n"
        f"• Required Joins: <code>{referral.get('required_joins', 10)}</code> friends\n"
        f"• Reward Duration: <code>{referral.get('reward_days', 5)}</code> days premium\n"
        f"• Reward Daily Limit: <code>{referral.get('reward_limit', 100)}</code> downloads\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )


def auto_delete_home(runtime: dict[str, Any]) -> str:
    settings = runtime.get("auto_delete") or {}
    dest_enabled = "🟢 Enabled" if settings.get("destination_enabled") else "🔴 Disabled"
    deliv_enabled = "🟢 Enabled" if settings.get("delivery_enabled") else "🔴 Disabled"
    return (
        "⏱️ <b>AUTO DELETE SETTINGS</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "⚙️ <b>Destination Channel Posts:</b>\n"
        f"• Status: {dest_enabled}\n"
        f"• Delay: <code>{human_seconds(settings.get('destination_seconds'))}</code>\n\n"
        "⚙️ <b>User-Delivered Videos:</b>\n"
        f"• Status: {deliv_enabled}\n"
        f"• Delay: <code>{human_seconds(settings.get('delivery_seconds'))}</code>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )


def broadcast_home(stats: dict[str, Any]) -> str:
    return (
        "📣 <b>ADVANCED BROADCAST SYSTEM</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"• 👥 <b>Target Audience Size:</b> <code>{stats.get('users', 0)}</code> users\n"
        f"• 📑 <b>Total Broadcasts Created:</b> <code>{stats.get('broadcasts', 0)}</code>\n\n"
        "<b>Instructions:</b>\n"
        "1. Tap <b>Start Broadcast</b> below.\n"
        "2. Send or forward any message (text, photo, video, etc.) to the bot.\n"
        "3. The bot will clone and broadcast it to all registered users.\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )


def diskwala_settings(runtime: dict[str, Any]) -> str:
    diskwala = runtime.get("diskwala", {})
    enabled = "🟢 Enabled" if diskwala.get("enabled") else "🔴 Disabled"
    api_key = diskwala.get("api_key") or "Not set"
    bot_username = diskwala.get("bot_username") or "Not set"
    return (
        "🔗 <b>DISKWALA MONETIZATION</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "Upload files to Diskwala automatically to earn money from your traffic.\n\n"
        f"• 📊 <b>Status:</b> {enabled}\n"
        f"• 🔑 <b>API Key:</b> <code>{api_key}</code>\n"
        f"• 🤖 <b>Uploader Bot:</b> <code>{bot_username}</code>\n\n"
        "<b>Requirements:</b>\n"
        "- <b>Userbot</b> must be logged in to forward files to the Uploader Bot.\n"
        "- The Uploader Bot must be started. If not, the userbot will do it.\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )
