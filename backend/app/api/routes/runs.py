"""Run control: start, heartbeat, stop, and the dashboard's live view."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.presenters import run_out
from app.api.schemas import (
    ActiveRunOut,
    HeartbeatOut,
    RunOut,
    StartRunOut,
    StartRunRequest,
    SearchPlanOut,
    StopRunRequest,
)
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, ExtensionAuth
from app.core.errors import Forbidden
from app.db.models import Preference, User
from app.safety import governor
from app.safety.policy import local_day_bounds, resolve_window, usage_snapshot
from app.core.timeutils import utcnow
from app.services import applications as applications_service
from app.services import runs as runs_service

router = APIRouter(prefix="/runs", tags=["runs"])


async def _require_owned_run(principal, db, run_id: uuid.UUID):
    return await runs_service.get_run(db, user_id=principal.user_id, run_id=run_id)


@router.post("/start", response_model=StartRunOut)
async def start_run(
    payload: StartRunRequest, principal: ExtensionAuth, db: DbSession
) -> StartRunOut:
    user = await db.get(User, principal.user_id)
    if user is None:
        raise Forbidden("Sign in again.")

    run = await runs_service.start_run(
        db, user=user, platform=payload.platform, dry_run=payload.dry_run
    )

    preference = await db.get(Preference, principal.user_id)
    snapshot = await usage_snapshot(
        db,
        user_id=principal.user_id,
        account_created_at=user.created_at,
        preferences=preference,
    )

    modes = list(preference.work_mode) if preference else []
    return StartRunOut(
        run=run_out(run),
        pacing=governor.next_pause(0).as_dict(),
        heartbeat_seconds=settings.safety_heartbeat_seconds,
        usage=snapshot.as_dict(),
        search=SearchPlanOut(
            roles=list(preference.target_roles) if preference else [],
            locations=list(preference.locations) if preference else [],
            work_mode=modes,
            remote_first="remote" in modes,
        ),
    )


@router.post("/{run_id}/heartbeat", response_model=HeartbeatOut)
async def heartbeat(
    run_id: uuid.UUID, principal: ExtensionAuth, db: DbSession
) -> HeartbeatOut:
    run = await _require_owned_run(principal, db, run_id)
    preference = await db.get(Preference, principal.user_id)
    run, decision = await runs_service.heartbeat(db, run=run, preferences=preference)

    return HeartbeatOut(
        run=run_out(run),
        allowed=decision.allowed,
        message=decision.message,
        reason=decision.reason,
        cooldown_until=decision.cooldown_until,
    )


@router.post("/{run_id}/stop", response_model=RunOut)
async def stop_run(
    run_id: uuid.UUID, payload: StopRunRequest, principal: ExtensionAuth, db: DbSession
) -> RunOut:
    run = await _require_owned_run(principal, db, run_id)
    run = await runs_service.stop_run(db, run=run, reason=payload.reason)
    return run_out(run)


@router.get("/active", response_model=ActiveRunOut)
async def active_run(user: CurrentUser, db: DbSession) -> ActiveRunOut:
    run = await runs_service.active_run(db, user_id=user.id)
    preference = await db.get(Preference, user.id)
    window = resolve_window(preference.active_hours if preference else None)
    day_start, _ = local_day_bounds(window, utcnow())

    today = await applications_service.today_counts(db, user_id=user.id, since=day_start)
    unresolved = await applications_service.unresolved_count(db, user_id=user.id)

    return ActiveRunOut(
        run=run_out(run) if run else None,
        today=today,
        unresolved=unresolved,
        heartbeat_seconds=settings.safety_heartbeat_seconds,
    )
