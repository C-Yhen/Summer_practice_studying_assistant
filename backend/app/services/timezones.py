from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_user_timezone(name: str | None) -> tuple[ZoneInfo | timezone, str]:
    """Return the saved IANA timezone, with an explicit UTC fallback."""
    try:
        return ZoneInfo(name or "UTC"), name or "UTC"
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc, "UTC"


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def local_date_range_utc(
    start: date, end: date, user_zone: ZoneInfo | timezone
) -> tuple[datetime, datetime]:
    """Convert inclusive local calendar dates into a UTC half-open range."""
    return (
        datetime.combine(start, time.min, user_zone).astimezone(timezone.utc),
        datetime.combine(end + timedelta(days=1), time.min, user_zone).astimezone(timezone.utc),
    )
