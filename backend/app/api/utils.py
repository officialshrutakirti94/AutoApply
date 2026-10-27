"""Small request helpers shared by routers."""

from __future__ import annotations

from datetime import datetime

from fastapi import Request

from app.core.timeutils import ensure_utc


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


def parse_datetime_param(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None
