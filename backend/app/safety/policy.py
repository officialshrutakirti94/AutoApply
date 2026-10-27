"""Deterministic safety policy.

These rules are code, not prompts: the LLM cannot widen a cap, extend a window or
cancel a cooldown. The same functions run at ``/runs/start``, on every heartbeat
and in the sweeper, so a stale run cannot outlive its permission.

Defaults are conservative guesses about platform tolerance, not measured limits.
Every ceiling below is hard-coded and cannot be raised by configuration.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.timeutils import ensure_utc, utcnow
from app.db.enums import ApplicationStatus, Platform, RunStatus
from app.db.models import AgentRun, Application, Preference, SafetyEvent
from app.safety import plans

log = get_logger("safety")

# Hard ceilings: configuration may lower these, never raise them.
HARD_DAILY_CEILING = 25
HARD_HOURLY_CEILING = 6
COUNTED_STATUSES = (ApplicationStatus.APPLIED.value, ApplicationStatus.DRY_RUN.value)


class PolicyReason:
    COOLDOWN = "cooldown"
    OUTSIDE_ACTIVE_HOURS = "outside_active_hours"
    REST_DAY = "rest_day"
    DAILY_CAP = "daily_cap"
    HOURLY_CAP = "hourly_cap"
    RUN_ALREADY_ACTIVE = "run_already_active"
    PLATFORM_NOT_ENABLED = "platform_not_enabled"
    RUN_WINDOW_EXPIRED = "run_window_expired"
    RUN_CAP_REACHED = "run_cap_reached"


@dataclass(frozen=True, slots=True)
class ActiveWindow:
    start_minute: int
    end_minute: int
    timezone_name: str
    timezone: ZoneInfo

    @property
    def wraps_midnight(self) -> bool:
        return self.end_minute <= self.start_minute

    def describe(self) -> str:
        return f"{_minutes_to_hhmm(self.start_minute)}-{_minutes_to_hhmm(self.end_minute)}"


@dataclass(slots=True)
class UsageSnapshot:
    applied_today: int
    applied_last_hour: int
    account_age_days: int
    warmup_cap: int
    effective_daily_cap: int
    effective_hourly_cap: int
    cooldown_until: datetime | None
    window: ActiveWindow
    rest_day: int
    day_reset_hour: int
    quota_resets_at: datetime | None
    plan: str = plans.DEFAULT_PLAN
    plan_label: str = "Regular"
    plan_daily_cap: int = 10
    plan_hourly_cap: int = 3
    llm_calls_per_day: int = 60

    def as_dict(self) -> dict:
        return {
            "applied_today": self.applied_today,
            "applied_last_hour": self.applied_last_hour,
            "account_age_days": self.account_age_days,
            "warmup_cap": self.warmup_cap,
            "effective_daily_cap": self.effective_daily_cap,
            "effective_hourly_cap": self.effective_hourly_cap,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "active_hours": self.window.describe(),
            "active_timezone": self.window.timezone_name,
            "rest_day": self.rest_day,
            "day_reset_hour": self.day_reset_hour,
            "quota_resets_at": self.quota_resets_at.isoformat() if self.quota_resets_at else None,
            "plan": self.plan,
            "plan_label": self.plan_label,
            "plan_daily_cap": self.plan_daily_cap,
            "plan_hourly_cap": self.plan_hourly_cap,
            "llm_calls_per_day": self.llm_calls_per_day,
        }


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    message: str = ""
    cooldown_until: datetime | None = None
    snapshot: UsageSnapshot | None = None
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "message": self.message,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "usage": self.snapshot.as_dict() if self.snapshot else None,
            "detail": self.detail,
        }


# ------------------------------------------------------------------ time helpers


def _minutes_to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hhmm_to_minutes(raw: str) -> int | None:
    try:
        hours, _, minutes = raw.strip().partition(":")
        total = int(hours) * 60 + int(minutes or 0)
    except (TypeError, ValueError):
        return None
    if not 0 <= total < 24 * 60:
        return None
    return total


def resolve_window(active_hours: dict | None) -> ActiveWindow:
    fallback_start, _, fallback_end = settings.safety_default_active_hours.partition("-")
    data = active_hours or {}

    # Explicit None checks, not `or`: "00:00" parses to 0, which is falsy and used
    # to fall back to 09:00. A user who asked for a midnight start got 09:00.
    start = _hhmm_to_minutes(str(data.get("start") or ""))
    if start is None:
        start = _hhmm_to_minutes(fallback_start)
    if start is None:
        start = 540

    end = _hhmm_to_minutes(str(data.get("end") or ""))
    if end is None:
        end = _hhmm_to_minutes(fallback_end)
    if end is None:
        end = 1260
    tz_name = str(data.get("timezone") or settings.safety_default_timezone)

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        # An unknown zone must not silently become UTC: the quota window and the
        # active hours would move without the user knowing.
        log.warning("unknown_timezone", requested=tz_name, fallback=settings.safety_default_timezone)
        tz_name = settings.safety_default_timezone
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            tz_name, tz = "UTC", timezone.utc  # type: ignore[assignment]

    return ActiveWindow(start_minute=start, end_minute=end, timezone_name=tz_name, timezone=tz)


def is_within_window(moment: datetime, window: ActiveWindow) -> bool:
    local = moment.astimezone(window.timezone)
    minute = local.hour * 60 + local.minute
    if window.wraps_midnight:
        return minute >= window.start_minute or minute < window.end_minute
    return window.start_minute <= minute < window.end_minute


def local_day_bounds(
    window: ActiveWindow, moment: datetime, reset_hour: int | None = None
) -> tuple[datetime, datetime]:
    """The quota window that ``moment`` falls in.

    The window does not roll over at midnight: it rolls over at
    ``SAFETY_DAY_RESET_HOUR`` (10:00 by default) in the user's own timezone, so a
    day's allowance starts in the morning and is used up during the working day.

    The returned window is always the one containing ``moment``, which means an
    application made at 09:00 and one made at 11:00 can land in different quota
    days. That is intended: the cap protects the account during one working day,
    not one calendar date.
    """
    hour = settings.safety_day_reset_hour if reset_hour is None else reset_hour
    hour = max(0, min(hour, 23))

    local = moment.astimezone(window.timezone)
    start_local = datetime.combine(local.date(), time(hour, 0), tzinfo=window.timezone)
    if local < start_local:
        # Still inside the window that began at the reset hour yesterday.
        start_local = start_local - timedelta(days=1)

    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


# ---------------------------------------------------------------------- usage


async def _count_applications(
    db: AsyncSession, *, user_id: uuid.UUID, since: datetime, until: datetime | None = None
) -> int:
    conditions = [
        Application.user_id == user_id,
        Application.status.in_(COUNTED_STATUSES),
        Application.created_at >= since,
    ]
    if until is not None:
        conditions.append(Application.created_at < until)
    total = await db.execute(select(func.count()).select_from(Application).where(*conditions))
    return int(total.scalar_one())


async def active_cooldown(db: AsyncSession, *, user_id: uuid.UUID) -> datetime | None:
    now = utcnow()
    row = (
        await db.execute(
            select(SafetyEvent.cooldown_until)
            .where(
                SafetyEvent.user_id == user_id,
                SafetyEvent.cooldown_until.is_not(None),
                SafetyEvent.cooldown_until > now,
            )
            .order_by(SafetyEvent.cooldown_until.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return ensure_utc(row)


async def has_active_cooldown(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
    return await active_cooldown(db, user_id=user_id) is not None


def _warmup_cap(account_age_days: int, daily_cap: int) -> int:
    warmup_days = max(settings.safety_warmup_days, 0)
    start_cap = settings.safety_warmup_start_cap
    if warmup_days == 0 or account_age_days >= warmup_days:
        return daily_cap
    ramp = start_cap + (daily_cap - start_cap) * (account_age_days / warmup_days)
    return max(min(int(ramp), daily_cap), start_cap)


async def usage_snapshot(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    account_created_at: datetime,
    preferences: Preference | None,
    plan: str | None = None,
) -> UsageSnapshot:
    now = utcnow()
    window = resolve_window(preferences.active_hours if preferences else None)

    limits = plans.limits_for(plan)

    # Entitlement = the tightest of: the user's own preference, their plan, the
    # deployment ceiling and the hard ceiling. A plan can never exceed the latter
    # two, and a preference can never exceed the plan.
    pref_daily = preferences.daily_cap if preferences else limits.daily_cap
    entitled_daily = max(
        1,
        min(pref_daily, limits.daily_cap, settings.safety_daily_cap, HARD_DAILY_CEILING),
    )
    entitled_hourly = max(
        1, min(limits.hourly_cap, settings.safety_hourly_cap, HARD_HOURLY_CEILING)
    )

    created = ensure_utc(account_created_at) or now
    account_age_days = max((now - created).days, 0)
    warmup_cap = _warmup_cap(account_age_days, entitled_daily)

    day_start, day_end = local_day_bounds(window, now)
    applied_today = await _count_applications(db, user_id=user_id, since=day_start, until=day_end)
    applied_last_hour = await _count_applications(
        db, user_id=user_id, since=now - timedelta(hours=1)
    )

    return UsageSnapshot(
        applied_today=applied_today,
        applied_last_hour=applied_last_hour,
        account_age_days=account_age_days,
        warmup_cap=warmup_cap,
        effective_daily_cap=min(entitled_daily, warmup_cap),
        effective_hourly_cap=entitled_hourly,
        cooldown_until=await active_cooldown(db, user_id=user_id),
        window=window,
        rest_day=settings.safety_rest_day,
        day_reset_hour=settings.safety_day_reset_hour,
        quota_resets_at=day_end,
        plan=limits.tier,
        plan_label=limits.label,
        plan_daily_cap=limits.daily_cap,
        plan_hourly_cap=limits.hourly_cap,
        llm_calls_per_day=min(limits.llm_calls_per_day, settings.llm_max_calls_per_day),
    )


# --------------------------------------------------------------------- decisions


async def check_platform_enabled(
    db: AsyncSession, *, user_id: uuid.UUID, platform: str
) -> PolicyDecision:
    preferences = await db.get(Preference, user_id)
    enabled = list(preferences.platforms) if preferences else []
    if enabled and platform not in enabled:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.PLATFORM_NOT_ENABLED,
            message=f"{platform.title()} is not one of your selected platforms.",
        )
    return PolicyDecision(allowed=True)


async def check_run_start(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    account_created_at: datetime,
    preferences: Preference | None,
    platform: str,
    plan: str | None = None,
    now: datetime | None = None,
) -> PolicyDecision:
    now = ensure_utc(now) or utcnow()
    snapshot = await usage_snapshot(
        db,
        user_id=user_id,
        account_created_at=account_created_at,
        preferences=preferences,
        plan=plan,
    )

    if snapshot.cooldown_until is not None:
        until = snapshot.cooldown_until.astimezone(snapshot.window.timezone)
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.COOLDOWN,
            message=f"Paused for safety until {until:%d %b, %H:%M}. Something on the platform looked like a check.",
            cooldown_until=snapshot.cooldown_until,
            snapshot=snapshot,
        )

    running = (
        await db.execute(
            select(AgentRun.id).where(
                AgentRun.user_id == user_id, AgentRun.status == RunStatus.RUNNING.value
            )
        )
    ).scalar_one_or_none()
    if running is not None:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.RUN_ALREADY_ACTIVE,
            message="A run is already active. Stop it before starting another.",
            snapshot=snapshot,
        )

    if platform not in {p.value for p in Platform}:
        return PolicyDecision(allowed=False, reason="unknown_platform", message="Unknown platform.")

    enabled = list(preferences.platforms) if preferences else []
    if enabled and platform not in enabled:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.PLATFORM_NOT_ENABLED,
            message=f"{platform.title()} is not one of your selected platforms.",
            snapshot=snapshot,
        )

    local_now = now.astimezone(snapshot.window.timezone)
    if local_now.weekday() == snapshot.rest_day:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.REST_DAY,
            message="Today is your weekly rest day. The agent resumes tomorrow.",
            snapshot=snapshot,
        )

    if not is_within_window(now, snapshot.window):
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.OUTSIDE_ACTIVE_HOURS,
            message=f"Outside your active hours ({snapshot.window.describe()} {snapshot.window.timezone_name}).",
            snapshot=snapshot,
        )

    if snapshot.applied_today >= snapshot.effective_daily_cap:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.DAILY_CAP,
            message=f"Daily limit reached ({snapshot.applied_today}/{snapshot.effective_daily_cap}). Resumes tomorrow.",
            snapshot=snapshot,
        )

    if snapshot.applied_last_hour >= snapshot.effective_hourly_cap:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.HOURLY_CAP,
            message="Hourly limit reached. Waiting it out keeps your account safe.",
            snapshot=snapshot,
        )

    return PolicyDecision(
        allowed=True,
        message="Ready.",
        snapshot=snapshot,
        detail={"remaining_today": max(snapshot.effective_daily_cap - snapshot.applied_today, 0)},
    )


async def check_run_progress(
    db: AsyncSession,
    *,
    run: AgentRun,
    preferences: Preference | None,
    now: datetime | None = None,
) -> PolicyDecision:
    """Called on heartbeat and before each step. Can only narrow, never widen."""
    now = ensure_utc(now) or utcnow()
    window = resolve_window(preferences.active_hours if preferences else None)
    cooldown_until = await active_cooldown(db, user_id=run.user_id)

    if cooldown_until is not None:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.COOLDOWN,
            message="Autopilot paused after a platform safety signal.",
            cooldown_until=cooldown_until,
        )

    if ensure_utc(run.window_end) and ensure_utc(run.window_end) <= now:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.RUN_WINDOW_EXPIRED,
            message="This run reached its time window.",
        )

    if run.applied_count + run.stuck_count >= run.max_applications:
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.RUN_CAP_REACHED,
            message="This run reached its application limit.",
        )

    if not is_within_window(now, window):
        return PolicyDecision(
            allowed=False,
            reason=PolicyReason.OUTSIDE_ACTIVE_HOURS,
            message=f"Outside your active hours ({window.describe()} {window.timezone_name}).",
        )

    return PolicyDecision(allowed=True)


async def llm_calls_in_window(
    db: AsyncSession, *, user_id: uuid.UUID, since: datetime
) -> int:
    """Model calls spent across every run started inside the quota window."""
    total = await db.execute(
        select(func.coalesce(func.sum(AgentRun.llm_calls), 0)).where(
            AgentRun.user_id == user_id, AgentRun.started_at >= since
        )
    )
    return int(total.scalar_one())


async def check_submit_allowed(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    account_created_at: datetime,
    preferences: Preference | None,
    plan: str | None = None,
    run_applied: int = 0,
    run_max: int = 0,
) -> tuple[bool, str]:
    """The last gate before an application is actually submitted.

    Checking the quota only when a run starts is not enough: a long run can
    outlive its allowance, and the extension is not trusted to stop on its own.
    So the submission itself is checked here, server side, on every single
    attempt. This is the check that protects the account.
    """
    snapshot = await usage_snapshot(
        db,
        user_id=user_id,
        account_created_at=account_created_at,
        preferences=preferences,
        plan=plan,
    )

    if snapshot.applied_today >= snapshot.effective_daily_cap:
        return False, PolicyReason.DAILY_CAP
    if snapshot.applied_last_hour >= snapshot.effective_hourly_cap:
        return False, PolicyReason.HOURLY_CAP
    if run_max and run_applied >= run_max:
        return False, PolicyReason.RUN_CAP_REACHED
    if snapshot.cooldown_until is not None:
        return False, PolicyReason.COOLDOWN
    return True, ""


# ------------------------------------------------------------------ hard stops

async def record_hard_stop(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID | None,
    event_type: str,
    detail: dict | None = None,
    cooldown_hours: int | None = None,
) -> SafetyEvent:
    hours = cooldown_hours if cooldown_hours is not None else settings.safety_cooldown_hours
    event = SafetyEvent(
        user_id=user_id,
        run_id=run_id,
        type=event_type,
        detail=detail or {},
        cooldown_until=utcnow() + timedelta(hours=hours) if hours > 0 else None,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
