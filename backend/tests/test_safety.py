"""Safety policy tests. The plan requires 100% here, so every rule has a test."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone


from app.core.config import settings
from app.core.timeutils import utcnow
from app.db.models import Application
from app.safety import governor
from app.safety.policy import (
    HARD_DAILY_CEILING,
    HARD_HOURLY_CEILING,
    PolicyReason,
    check_run_progress,
    check_run_start,
    has_active_cooldown,
    record_hard_stop,
    resolve_window,
    usage_snapshot,
)
from app.safety.sweeper import sweep_once
from tests.helpers import (
    complete_onboarding,
    connect_extension,
    extension_headers,
    make_preferences,
    make_user,
    start_run,
)


async def _seed(db, *, applied_today: int = 0, **preference_overrides):
    user = await make_user(db)
    preferences = await make_preferences(db, user.id, **preference_overrides)
    for index in range(applied_today):
        db.add(
            Application(
                user_id=user.id,
                platform="linkedin",
                job_id=f"job-{index}",
                status="applied",
                created_at=utcnow(),
            )
        )
    await db.commit()
    return user, preferences


async def _check(db, user, preferences, *, now=None, platform="linkedin"):
    return await check_run_start(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
        platform=platform,
        now=now,
    )


async def test_start_is_allowed_when_clean(db):
    user, preferences = await _seed(db)
    decision = await _check(db, user, preferences)
    assert decision.allowed is True
    assert decision.snapshot is not None
    assert decision.snapshot.applied_today == 0


async def test_daily_cap_blocks_start(db):
    user, preferences = await _seed(db, applied_today=3, daily_cap=3)
    decision = await _check(db, user, preferences)
    assert decision.allowed is False
    assert decision.reason == PolicyReason.DAILY_CAP


async def test_hourly_cap_blocks_start(db):
    user, preferences = await _seed(db, applied_today=3, daily_cap=10)
    decision = await _check(db, user, preferences)
    assert decision.allowed is False
    assert decision.reason == PolicyReason.HOURLY_CAP


async def test_cooldown_blocks_start(db):
    user, preferences = await _seed(db)
    await record_hard_stop(
        db, user_id=user.id, run_id=None, event_type="captcha", cooldown_hours=24
    )
    assert await has_active_cooldown(db, user_id=user.id) is True

    decision = await _check(db, user, preferences)
    assert decision.allowed is False
    assert decision.reason == PolicyReason.COOLDOWN
    assert decision.cooldown_until is not None


async def test_outside_active_hours_blocks_start(db):
    user, preferences = await _seed(
        db, active_hours={"start": "03:00", "end": "03:30", "timezone": "UTC"}
    )
    midday = datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)
    decision = await _check(db, user, preferences, now=midday)
    assert decision.allowed is False
    assert decision.reason == PolicyReason.OUTSIDE_ACTIVE_HOURS


async def test_active_window_can_wrap_midnight(db):
    user, preferences = await _seed(
        db, active_hours={"start": "22:00", "end": "04:00", "timezone": "UTC"}
    )
    late = datetime(2026, 5, 12, 23, 30, tzinfo=timezone.utc)
    decision = await _check(db, user, preferences, now=late)
    assert decision.allowed is True


async def test_rest_day_blocks_start(db, monkeypatch):
    now = datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(settings, "safety_rest_day", now.weekday())

    user, preferences = await _seed(db)
    decision = await _check(db, user, preferences, now=now)
    assert decision.allowed is False
    assert decision.reason == PolicyReason.REST_DAY


async def test_platform_must_be_enabled(db):
    user, preferences = await _seed(db, platforms=["naukri"])
    decision = await _check(db, user, preferences, platform="linkedin")
    assert decision.allowed is False
    assert decision.reason == PolicyReason.PLATFORM_NOT_ENABLED


async def test_warmup_limits_a_new_account(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 14)
    monkeypatch.setattr(settings, "safety_warmup_start_cap", 5)

    user, preferences = await _seed(db, daily_cap=10)
    snapshot = await usage_snapshot(
        db, user_id=user.id, account_created_at=user.created_at, preferences=preferences
    )
    assert snapshot.effective_daily_cap == 5


async def test_warmup_lifts_after_the_ramp(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 14)
    monkeypatch.setattr(settings, "safety_warmup_start_cap", 5)

    user, preferences = await _seed(db, daily_cap=10)
    old_account = utcnow() - timedelta(days=30)
    snapshot = await usage_snapshot(
        db, user_id=user.id, account_created_at=old_account, preferences=preferences
    )
    assert snapshot.effective_daily_cap == 10


async def test_hard_ceilings_cannot_be_raised_by_configuration(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_daily_cap", 500)
    monkeypatch.setattr(settings, "safety_hourly_cap", 500)

    user, preferences = await _seed(db, daily_cap=25)
    snapshot = await usage_snapshot(
        db, user_id=user.id, account_created_at=user.created_at, preferences=preferences
    )
    assert snapshot.effective_daily_cap <= HARD_DAILY_CEILING
    assert snapshot.effective_hourly_cap <= HARD_HOURLY_CEILING


async def test_second_run_is_rejected(client_factory):
    alice = client_factory()
    await alice.post("/api/auth/dev-login", json={"email": "one-run@example.com"})
    await complete_onboarding(alice)
    token = await connect_extension(alice, install_id="one-run")

    await start_run(alice, token)

    response = await alice.post(
        "/api/runs/start",
        json={"platform": "linkedin", "dry_run": False},
        headers=extension_headers(token),
    )
    assert response.status_code in {403, 409}


async def test_stale_heartbeat_is_marked_interrupted(client_factory, db):
    from app.db.models import AgentRun

    alice = client_factory()
    await alice.post("/api/auth/dev-login", json={"email": "stale@example.com"})
    await complete_onboarding(alice)
    token = await connect_extension(alice, install_id="stale")
    run = await start_run(alice, token)

    stored = await db.get(AgentRun, uuid.UUID(run["id"]))
    stored.last_heartbeat_at = utcnow() - timedelta(minutes=30)
    await db.commit()

    report = await sweep_once(db)
    assert report.interrupted_runs == 1

    await db.refresh(stored)
    assert stored.status == "interrupted"
    assert stored.stop_reason == "heartbeat_timeout"

    response = await alice.post(
        f"/api/runs/{run['id']}/heartbeat", headers=extension_headers(token)
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False


async def test_heartbeat_stops_the_run_outside_active_hours(client_factory, db):
    from app.db.models import AgentRun, Preference as PreferenceModel

    alice = client_factory()
    await alice.post("/api/auth/dev-login", json={"email": "hours@example.com"})
    await complete_onboarding(alice)
    token = await connect_extension(alice, install_id="hours")
    run = await start_run(alice, token)

    # A window two hours ahead can never contain "now", whatever time the suite runs.
    ahead = utcnow() + timedelta(hours=2)
    later = utcnow() + timedelta(hours=3)

    stored_run = await db.get(AgentRun, uuid.UUID(run["id"]))
    preference = await db.get(PreferenceModel, stored_run.user_id)
    preference.active_hours = {
        "start": ahead.strftime("%H:%M"),
        "end": later.strftime("%H:%M"),
        "timezone": "UTC",
    }
    await db.commit()

    response = await alice.post(
        f"/api/runs/{run['id']}/heartbeat", headers=extension_headers(token)
    )
    body = response.json()
    assert body["allowed"] is False
    assert body["reason"] == PolicyReason.OUTSIDE_ACTIVE_HOURS
    assert body["run"]["status"] in {"stopped", "done"}


async def test_run_progress_respects_the_run_window(db):
    user, preferences = await _seed(db)
    from app.db.models import AgentRun

    run = AgentRun(
        user_id=user.id,
        platform="linkedin",
        status="running",
        dry_run=True,
        started_at=utcnow() - timedelta(hours=3),
        last_heartbeat_at=utcnow(),
        window_end=utcnow() - timedelta(minutes=1),
        max_applications=10,
    )
    db.add(run)
    await db.commit()

    decision = await check_run_progress(db, run=run, preferences=preferences)
    assert decision.allowed is False
    assert decision.reason == PolicyReason.RUN_WINDOW_EXPIRED


async def test_run_progress_respects_the_application_cap(db):
    user, preferences = await _seed(db)
    from app.db.models import AgentRun

    run = AgentRun(
        user_id=user.id,
        platform="linkedin",
        status="running",
        dry_run=True,
        started_at=utcnow(),
        last_heartbeat_at=utcnow(),
        window_end=utcnow() + timedelta(hours=1),
        max_applications=3,
        applied_count=3,
    )
    db.add(run)
    await db.commit()

    decision = await check_run_progress(db, run=run, preferences=preferences)
    assert decision.allowed is False
    assert decision.reason == PolicyReason.RUN_CAP_REACHED


def test_governor_delays_stay_within_bounds():
    for _ in range(50):
        delay = governor.action_delay_ms()
        assert 250 <= delay <= 6000

        pause = governor.apply_pause_s()
        assert 30 <= pause <= 600


def test_governor_never_goes_below_the_floor():
    assert governor.enforce_floor(0) == governor.MIN_ACTION_DELAY_MS
    assert governor.enforce_floor(-500) == governor.MIN_ACTION_DELAY_MS
    assert governor.enforce_floor(10_000) == 10_000


def test_long_break_every_n_applications():
    assert governor.long_break_s(0) is None
    assert governor.long_break_s(3) is None
    assert governor.long_break_s(settings.safety_long_break_every_n) is not None


def test_error_limit_triggers_hard_stop():
    assert governor.reached_error_limit(2) is False
    assert governor.reached_error_limit(3) is True


async def test_preferences_validation_rejects_caps_above_ceiling(onboarded):
    response = await onboarded.put("/api/preferences", json={"daily_cap": 100})
    assert response.status_code == 422


async def test_safety_status_reports_usage(onboarded):
    body = (await onboarded.get("/api/safety/status")).json()
    assert body["usage"]["effective_daily_cap"] <= HARD_DAILY_CEILING
    assert body["daily_ceilings"]["hard_daily"] == HARD_DAILY_CEILING
    assert "active_hours" in body["usage"]


def test_a_midnight_start_is_not_replaced_by_the_default(db):
    """`00:00` parses to 0, which is falsy; it used to fall back to 09:00."""
    window = resolve_window({"start": "00:00", "end": "23:59", "timezone": "UTC"})
    assert window.start_minute == 0
    assert window.end_minute == 23 * 60 + 59
    assert window.describe() == "00:00-23:59"


def test_an_invalid_window_falls_back_to_the_configured_default():
    window = resolve_window({"start": "99:99", "end": "", "timezone": "UTC"})
    start, _, end = settings.safety_default_active_hours.partition("-")
    assert window.describe() == f"{start}-{end}"
