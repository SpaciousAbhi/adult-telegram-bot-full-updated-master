from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required deployment configuration is invalid."""


def _first_env(names: Iterable[str]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _parse_int_set(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError as exc:
            raise ConfigError(f"Invalid admin id: {part}") from exc
    return frozenset(ids)


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer value: {raw}") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _validate_database_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme in {"mongodb", "mongodb+srv"}:
        return
    if parsed.scheme.startswith("postgres"):
        raise ConfigError(
            "DATABASE_URL points to PostgreSQL, but this bot preserves users in MongoDB. "
            "Set MONGO_URI/MONGODB_URI, or set DATABASE_URL to a MongoDB URI."
        )
    raise ConfigError("Database URL must start with mongodb:// or mongodb+srv://")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_url: str
    database_name: str
    api_id: int | None
    api_hash: str | None
    poll_interval_seconds: int
    task_batch_limit: int
    local_mode: bool = False

    @property
    def primary_admin_id(self) -> int:
        if not self.admin_ids:
            raise ConfigError("ADMIN_ID or OWNER_ID is required")
        return sorted(self.admin_ids)[0]

    @property
    def userbot_enabled(self) -> bool:
        return self.api_id is not None and bool(self.api_hash)

    def require_userbot_credentials(self) -> None:
        if not self.userbot_enabled:
            raise ConfigError("API_ID and API_HASH are required for userbot login and source scanning")


def load_settings() -> Settings:
    token = _first_env(["BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TOKEN"])
    admin_ids = _parse_int_set(_first_env(["ADMIN_ID", "OWNER_ID", "BOT_OWNER_ID"]))
    database_url = _first_env(
        [
            "MONGO_URI",
            "MONGODB_URI",
            "MONGO_URL",
            "MONGODB_URL",
            "MONGO_DB_URI",
            "MONGO_DB_URL",
            "DATABASE_URL",
        ]
    )
    if not token:
        raise ConfigError("BOT_TOKEN is required")
    if not admin_ids:
        raise ConfigError("ADMIN_ID is required")
    if not database_url:
        raise ConfigError("MONGO_URI is required")
    _validate_database_url(database_url)

    return Settings(
        bot_token=token,
        admin_ids=admin_ids,
        database_url=database_url,
        database_name=os.getenv("MONGO_DATABASE", "adult_telegram_bot").strip() or "adult_telegram_bot",
        api_id=_parse_optional_int(_first_env(["API_ID", "TELEGRAM_API_ID"])),
        api_hash=_first_env(["API_HASH", "TELEGRAM_API_HASH"]),
        poll_interval_seconds=max(5, _int_env("POLL_INTERVAL_SECONDS", 15)),
        task_batch_limit=max(1, _int_env("TASK_BATCH_LIMIT", 20)),
        local_mode=os.getenv("LOCAL_MODE", "").strip().lower() in {"1", "true", "yes"},
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()

