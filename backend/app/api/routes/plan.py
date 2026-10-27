"""Plan entitlements: what the user is on, and what it allows.

No payment provider in v1. The tier is a flag the team can set, and the switch
endpoint below exists so the flow can be demonstrated end to end. It is disabled in
production so a client can never grant itself Pro Plus.

Switching a plan does not silently raise a *user's own* cap if they deliberately
lowered it: the preference is only bumped when it still equals the old plan's cap.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PlanLimitsOut, PlanOut, PlanSwitchRequest
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFound
from app.db.models import Preference
from app.safety import plans
from app.safety.policy import usage_snapshot

router = APIRouter(prefix="/plan", tags=["plan"])


async def _snapshot(db: AsyncSession, user, plan: str):
    preference = await db.get(Preference, user.id)
    return await usage_snapshot(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preference,
        plan=plan,
    )


def _payload(plan: str, snapshot) -> PlanOut:
    limits = plans.limits_for(plan)
    return PlanOut(
        plan=limits.tier,
        label=limits.label,
        limits=PlanLimitsOut(**limits.as_dict()),
        usage=snapshot.as_dict(),
        available=[PlanLimitsOut(**item) for item in plans.catalogue()],
    )


@router.get("", response_model=PlanOut)
async def read_plan(user: CurrentUser, db: DbSession) -> PlanOut:
    """The plan card: current tier, its limits, today's usage, and the others."""
    snapshot = await _snapshot(db, user, user.plan)
    return _payload(user.plan, snapshot)


@router.post("/switch", response_model=PlanOut)
async def switch_plan(payload: PlanSwitchRequest, user: CurrentUser, db: DbSession) -> PlanOut:
    """Demo-only plan change. Returns 404 in production, like dev-login."""
    if settings.is_production:
        raise NotFound("Not found.")

    previous = plans.limits_for(user.plan)
    target = plans.limits_for(payload.plan)

    user.plan = target.tier

    preference = await db.get(Preference, user.id)
    if preference is not None and preference.daily_cap == previous.daily_cap:
        # Not customised by the user, so move the cap with the plan.
        preference.daily_cap = target.daily_cap

    await db.commit()
    await db.refresh(user)

    snapshot = await _snapshot(db, user, target.tier)
    return _payload(target.tier, snapshot)
