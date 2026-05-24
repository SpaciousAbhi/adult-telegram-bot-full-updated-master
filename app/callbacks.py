from __future__ import annotations

MAX_CALLBACK_BYTES = 64


def cb(*parts: object) -> str:
    value = ":".join(str(part) for part in parts if part is not None)
    if len(value.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise ValueError(f"Callback is too long: {value}")
    return value


def split_cb(data: str | None) -> list[str]:
    if not data:
        return []
    return data.split(":")


def is_prefix(data: str | None, *parts: str) -> bool:
    tokens = split_cb(data)
    return tokens[: len(parts)] == list(parts)


ADMIN_HOME = cb("admin", "home")
TASKS_HOME = cb("tasks", "home")
USERBOT_HOME = cb("userbot", "home")
FORCE_HOME = cb("force", "home")
ACCESS_HOME = cb("access", "home")
BROADCAST_HOME = cb("broadcast", "home")
AUTO_DELETE_HOME = cb("autodel", "home")
FORWARD_TAG_TOGGLE = cb("settings", "forward_tag")
FORCE_VERIFY = cb("force", "verify")
DISK_HOME = cb("disk", "home")
