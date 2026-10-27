"""Maintenance endpoints for an external scheduler.

The in-process maintenance loop handles a single instance. If the API is ever
scaled, disable the loop and point a cron at this route instead.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.core.config import settings
from app.core.deps import DbSession
from app.core.errors import Forbidden, NotFound
from app.core.security import signatures_match
from app.safety.sweeper import sweep_once

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/sweep")
async def sweep(
    request: Request,
    db: DbSession,
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    full: bool = True,
) -> dict:
    if not settings.cron_secret:
        raise NotFound("Not found.")
    if not x_cron_secret or not signatures_match(settings.cron_secret, x_cron_secret):
        raise Forbidden("Invalid cron secret.")

    report = await sweep_once(db, full=full)
    return {"ok": True, **report.as_dict()}
