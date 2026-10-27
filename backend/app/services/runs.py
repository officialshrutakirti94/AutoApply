"""Run lifecycle: start, heartbeat, stop, and one agent step.

All policy checks funnel through ``app.safety.policy``. This module never decides
whether something is *safe*; it only applies the decision and records the result.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import StepContext
from app.agents.graph import StepOutcome, run_agent_step
from app.contract.models import ActionType, AgentResponse, Observation, Signal, StepStatus
from app.core.config import settings
from app.core.errors import Conflict, NotFound, PolicyBlocked
from app.core.logging import get_logger
from app.core.timeutils import ensure_utc, utcnow
from app.db.enums import ApplicationReason, ApplicationStatus, RunStatus
from app.db.models import AgentRun, Preference, Profile, User
from app.safety import plans, policy
from app.safety.policy import local_day_bounds, resolve_window
from app.services import applications as applications_service

log = get_logger("runs")

_COOLDOWN_BY_SIGNAL: dict[str, int] = {
    Signal.CAPTCHA.value: 48,
    Signal.CHECKPOINT.value: 48,
    Signal.WARNING_BANNER.value: 24,
    Signal.FORCED_LOGOUT.value: 24,
    Signal.RATE_LIMITED.value: 24,
}

_COUNTING_STATUSES = {ApplicationStatus.APPLIED.value, ApplicationStatus.DRY_RUN.value}


async def get_run(db: AsyncSession, *, user_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
    run = (
        await db.execute(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise NotFound("That run no longer exists.")
    return run


async def active_run(db: AsyncSession, *, user_id: uuid.UUID) -> AgentRun | None:
    return (
        await db.execute(
            select(AgentRun)
            .where(AgentRun.user_id == user_id, AgentRun.status == RunStatus.RUNNING.value)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _finish(run: AgentRun, *, status: str, reason: str | None, now=None) -> None:
    run.status = status
    run.ended_at = now or utcnow()
    run.stop_reason = reason


async def start_run(
    db: AsyncSession,
    *,
    user: User,
    platform: str,
    dry_run: bool,
) -> AgentRun:
    # A run whose tab died keeps its row (and its heartbeat stops), so the next
    # attempt used to be refused forever. Reclaim it first: the sweeper does this
    # eventually, but the user should not have to wait for it.
    stuck = (
        await db.execute(
            select(AgentRun).where(
                AgentRun.user_id == user.id, AgentRun.status == RunStatus.RUNNING.value
            )
        )
    ).scalar_one_or_none()
    if stuck is not None:
        await interrupt_if_stale(db, run=stuck)

    preferences = await db.get(Preference, user.id)
    decision = await policy.check_run_start(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
        platform=platform,
        plan=user.plan,
    )
    if not decision.allowed:
        raise PolicyBlocked(decision.message, details=decision.as_dict())

    snapshot = decision.snapshot
    remaining_today = (
        snapshot.effective_daily_cap - snapshot.applied_today if snapshot is not None else 10
    )
    max_applications = max(1, min(settings.safety_max_run_applications, remaining_today))

    now = utcnow()
    run = AgentRun(
        user_id=user.id,
        platform=platform,
        status=RunStatus.RUNNING.value,
        dry_run=dry_run,
        started_at=now,
        last_heartbeat_at=now,
        window_end=now + timedelta(minutes=settings.safety_run_window_minutes),
        max_applications=max_applications,
        agent_state={
            "started_with": {
                "daily_cap": snapshot.effective_daily_cap if snapshot else None,
                "hourly_cap": snapshot.effective_hourly_cap if snapshot else None,
                "applied_today": snapshot.applied_today if snapshot else 0,
            }
        },
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        # The partial unique index rejected a second running row.
        await db.rollback()
        raise Conflict("A run is already active. Stop it before starting another.")
    await db.refresh(run)
    return run


async def stop_run(db: AsyncSession, *, run: AgentRun, reason: str | None = None) -> AgentRun:
    if run.status == RunStatus.RUNNING.value:
        _finish(run, status=RunStatus.STOPPED.value, reason=reason or "user_stopped")
        await db.commit()
    await db.refresh(run)
    return run


async def interrupt_if_stale(db: AsyncSession, *, run: AgentRun) -> bool:
    heartbeat_at = ensure_utc(run.last_heartbeat_at)
    if heartbeat_at is None:
        return False
    if run.status != RunStatus.RUNNING.value:
        return False
    if (utcnow() - heartbeat_at).total_seconds() <= settings.safety_heartbeat_timeout_seconds:
        return False

    _finish(run, status=RunStatus.INTERRUPTED.value, reason="heartbeat_timeout")
    await db.commit()
    return True


async def heartbeat(
    db: AsyncSession, *, run: AgentRun, preferences: Preference | None
) -> tuple[AgentRun, policy.PolicyDecision]:
    if run.status != RunStatus.RUNNING.value:
        # The run was stopped or swept as interrupted; a late heartbeat must not
        # revive it.
        return run, policy.PolicyDecision(
            allowed=False,
            reason="run_not_active",
            message="This run is no longer active.",
        )

    run.last_heartbeat_at = utcnow()
    decision = await policy.check_run_progress(db, run=run, preferences=preferences)

    if not decision.allowed:
        reason = decision.reason or "policy_stop"
        if reason == policy.PolicyReason.COOLDOWN:
            _finish(run, status=RunStatus.STOPPED.value, reason=reason)
        elif reason == policy.PolicyReason.RUN_WINDOW_EXPIRED:
            _finish(run, status=RunStatus.DONE.value, reason=reason)
        elif reason == policy.PolicyReason.RUN_CAP_REACHED:
            _finish(run, status=RunStatus.DONE.value, reason=ApplicationReason.CAP_REACHED.value)
        else:
            _finish(run, status=RunStatus.STOPPED.value, reason=reason)

    await db.commit()
    await db.refresh(run)
    return run, decision


async def process_step(db: AsyncSession, *, run: AgentRun, observation: Observation) -> StepOutcome:
    """Run one agent decision and write everything it implies."""
    if run.status != RunStatus.RUNNING.value:
        raise Conflict("This run is not active.")
    if observation.platform.value != run.platform:
        raise Conflict("That observation belongs to a different platform.")

    profile = await db.get(Profile, run.user_id)
    preferences = await db.get(Preference, run.user_id)
    user = await db.get(User, run.user_id)

    # Model budget for this step: the tighter of "this run" and "this quota day".
    window = resolve_window(preferences.active_hours if preferences else None)
    day_start, _ = local_day_bounds(window, utcnow())
    llm_spent_today = await policy.llm_calls_in_window(
        db, user_id=run.user_id, since=day_start
    )
    run_budget = max(settings.llm_max_calls_per_run - run.llm_calls, 0)
    plan_daily_llm = min(
        plans.limits_for(user.plan if user else None).llm_calls_per_day,
        settings.llm_max_calls_per_day,
    )
    day_budget = max(plan_daily_llm - llm_spent_today, 0)

    ctx = StepContext(
        db=db,
        user_id=run.user_id,
        run=run,
        profile=profile,
        preferences=preferences,
        llm_calls_left=min(run_budget, day_budget),
        dry_run=run.dry_run,
    )

    outcome = await run_agent_step(ctx, observation)
    run.llm_calls += outcome.llm_calls

    # The quota is checked on the submission itself, not only when the run
    # started: a long run can outlive its allowance, and the extension is not
    # trusted to stop by itself.
    quota_blocked = False
    if any(action.type is ActionType.SUBMIT for action in outcome.response.actions):
        allowed, reason = await policy.check_submit_allowed(
            db,
            user_id=run.user_id,
            account_created_at=user.created_at if user else utcnow(),
            preferences=preferences,
            plan=user.plan if user else None,
            run_applied=run.applied_count,
            run_max=run.max_applications,
        )
        if not allowed:
            quota_blocked = True
            log.warning(
                "submit_blocked_by_quota",
                run_id=str(run.id),
                reason=reason,
                applied_today=run.applied_count,
            )
            outcome.response = AgentResponse(
                actions=[
                    action
                    for action in outcome.response.actions
                    if action.type is not ActionType.SUBMIT
                ],
                status=StepStatus.DONE,
                reason=ApplicationReason.CAP_REACHED.value,
            )
            outcome.job_status = ApplicationStatus.SKIPPED.value
            outcome.job_reason = ApplicationReason.CAP_REACHED.value

    if outcome.job_status:
        _application, changed = await applications_service.record(
            db,
            user_id=run.user_id,
            run_id=run.id,
            observation=observation,
            status=outcome.job_status,
            reason=outcome.job_reason,
            answers_used=outcome.answers_used,
            trace_id=outcome.trace_id,
        )
        # Counters only move when the ledger row actually changed, so a repeated
        # confirmation for the same job cannot inflate the run.
        if changed:
            if outcome.job_status in _COUNTING_STATUSES:
                run.applied_count += 1
            elif outcome.job_status == ApplicationStatus.SKIPPED.value:
                run.skipped_count += 1
            elif outcome.job_status in {
                ApplicationStatus.NEEDS_ATTENTION.value,
                ApplicationStatus.FAILED.value,
            }:
                run.stuck_count += 1

    stop_reason: str | None = None
    hard_signal = next(
        (signal for signal in observation.signals if signal in {*_COOLDOWN_BY_SIGNAL}), None
    )

    if outcome.response.status is StepStatus.STOP:
        stop_reason = outcome.job_reason or ApplicationReason.SECURITY_CHECKPOINT.value
        _finish(run, status=RunStatus.STOPPED.value, reason=stop_reason)
        if hard_signal is not None:
            await policy.record_hard_stop(
                db,
                user_id=run.user_id,
                run_id=run.id,
                event_type=hard_signal.value,
                detail={"platform": run.platform, "job_id": observation.job.id},
                cooldown_hours=_COOLDOWN_BY_SIGNAL[hard_signal.value],
            )
    elif quota_blocked:
        # The daily or hourly allowance is gone: stop the run rather than keep
        # filling forms that can never be submitted.
        _finish(run, status=RunStatus.DONE.value, reason=ApplicationReason.CAP_REACHED.value)
    elif run.applied_count + run.stuck_count >= run.max_applications:
        _finish(run, status=RunStatus.DONE.value, reason=ApplicationReason.CAP_REACHED.value)
    else:
        run.agent_state = {
            "last_route": outcome.route,
            "last_status": outcome.response.status.value,
            "last_reason": outcome.response.reason,
            "last_job_id": observation.job.id,
            "last_page_type": observation.page_type.value,
        }

    await db.commit()
    await db.refresh(run)

    log.info(
        "agent_step",
        run_id=str(run.id),
        platform=run.platform,
        page=observation.page_type.value,
        route=outcome.route,
        status=outcome.response.status.value,
        job_status=outcome.job_status,
        reason=outcome.response.reason,
    )
    return outcome
