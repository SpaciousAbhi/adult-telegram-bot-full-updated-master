from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, timezone


IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def utcnow() -> datetime:
    return datetime.now(UTC)


def utc_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or utcnow()
    start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def human_seconds(seconds: int | None) -> str:
    if not seconds:
        return "off"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def compact_dt(value: datetime | None) -> str:
    if not value:
        return "never"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def compact_dt_utc(value: datetime | None) -> str:
    if not value:
        return "never"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
