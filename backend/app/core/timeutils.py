"""Time helpers. Everything is stored timezone-aware in UTC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Guard against naive datetimes coming back from SQLite in tests."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def ago(**kwargs: float) -> datetime:
    return utcnow() - timedelta(**kwargs)


def in_future(**kwargs: float) -> datetime:
    return utcnow() + timedelta(**kwargs)
