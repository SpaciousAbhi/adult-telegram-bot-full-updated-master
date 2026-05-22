from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.timeutils import utc_day_bounds, utcnow


PREMIUM_FALLBACK_LIMIT = 1_000_000


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    limit: int
    used: int
    reason: str = ""

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def normalize_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return None


def is_until_active(value: Any, now: datetime | None = None) -> bool:
    expires_at = normalize_datetime(value)
    if not expires_at:
        return False
    return expires_at > (now or utcnow())


def effective_daily_limit(
    user: dict[str, Any] | None,
    runtime_settings: dict[str, Any],
    now: datetime | None = None,
) -> int:
    now = now or utcnow()
    user = user or {}
    access = runtime_settings.get("access") or {}
    base_limit = int(access.get("free_daily_limit") or 5)

    if user.get("plan") == "premium" and is_until_active(user.get("premium_until"), now):
        return int(access.get("premium_daily_limit") or PREMIUM_FALLBACK_LIMIT)

    if is_until_active(user.get("referral_reward_until"), now):
        reward_limit = user.get("referral_reward_limit")
        if reward_limit:
            return max(base_limit, int(reward_limit))

    return base_limit


def decide_access(
    user: dict[str, Any] | None,
    runtime_settings: dict[str, Any],
    downloads_today: int,
    now: datetime | None = None,
) -> AccessDecision:
    limit = effective_daily_limit(user, runtime_settings, now)
    if downloads_today >= limit:
        return AccessDecision(False, limit, downloads_today, "daily_limit_exhausted")
    return AccessDecision(True, limit, downloads_today)


def today_query(now: datetime | None = None) -> dict[str, Any]:
    start, end = utc_day_bounds(now)
    return {"downloaded_at": {"$gte": start, "$lt": end}}

