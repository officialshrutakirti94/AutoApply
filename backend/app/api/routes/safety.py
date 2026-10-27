"""What the dashboard shows about caps, cooldown and active hours."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import SafetyStatusOut
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.timeutils import utcnow
from app.db.models import Preference
from app.safety.policy import (
    HARD_DAILY_CEILING,
    HARD_HOURLY_CEILING,
    is_within_window,
    usage_snapshot,
)

router = APIRouter(prefix="/safety", tags=["safety"])


@router.get("/status", response_model=SafetyStatusOut)
async def safety_status(user: CurrentUser, db: DbSession) -> SafetyStatusOut:
    preference = await db.get(Preference, user.id)
    snapshot = await usage_snapshot(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preference,
        plan=user.plan,
    )

    now = utcnow()
    local_now = now.astimezone(snapshot.window.timezone)

    allowed = True
    reason: str | None = None
    message = "Ready."

    if snapshot.cooldown_until is not None:
        allowed, reason = False, "cooldown"
        message = (
            f"Paused until {snapshot.cooldown_until.astimezone(snapshot.window.timezone):%d %b, %H:%M}."
        )
    elif local_now.weekday() == snapshot.rest_day:
        allowed, reason = False, "rest_day"
        message = "Today is your weekly rest day."
    elif not is_within_window(now, snapshot.window):
        allowed, reason = False, "outside_active_hours"
        message = f"Outside your active hours ({snapshot.window.describe()} {snapshot.window.timezone_name})."
    elif snapshot.applied_today >= snapshot.effective_daily_cap:
        allowed, reason = False, "daily_cap"
        message = f"Daily limit reached ({snapshot.applied_today}/{snapshot.effective_daily_cap})."
    elif snapshot.applied_last_hour >= snapshot.effective_hourly_cap:
        allowed, reason = False, "hourly_cap"
        message = "Hourly limit reached."

    return SafetyStatusOut(
        allowed=allowed,
        message=message,
        reason=reason,
        cooldown_until=snapshot.cooldown_until,
        usage=snapshot.as_dict(),
        daily_ceilings={
            "configured_daily": settings.safety_daily_cap,
            "configured_hourly": settings.safety_hourly_cap,
            "hard_daily": HARD_DAILY_CEILING,
            "hard_hourly": HARD_HOURLY_CEILING,
        },
    )
