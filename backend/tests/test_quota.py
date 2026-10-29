"""The quota: how many, when it resets, and who enforces it.

The account-safety promise is that the agent cannot apply more than the user
allows. That is only true if the **server** enforces it at the moment of
submission, not merely when a run starts. These tests cover both the arithmetic
and the enforcement point.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone


from app.core.config import settings
from app.core.timeutils import utcnow
from app.db.enums import ApplicationStatus
from app.safety.policy import (
    PolicyReason,
    check_submit_allowed,
    local_day_bounds,
    resolve_window,
    usage_snapshot,
)
from tests.helpers import (
    agent_step,
    button,
    complete_onboarding,
    connect_extension,
    extension_headers,
    make_preferences,
    make_user,
    observation,
    start_run,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _window(tz: str = "Asia/Kolkata"):
    return resolve_window({"start": "00:00", "end": "23:59", "timezone": tz})


# --------------------------------------------------------------- the reset hour


def test_quota_day_rolls_over_at_ten_in_the_morning():
    window = _window()
    reset_hour = settings.safety_day_reset_hour
    assert reset_hour == 10

    # 11:00 on the 12th: the window started at 10:00 on the 12th.
    start, end = local_day_bounds(window, datetime(2026, 5, 12, 11, 0, tzinfo=IST))
    assert start == datetime(2026, 5, 12, 10, 0, tzinfo=IST).astimezone(timezone.utc)
    assert end == datetime(2026, 5, 13, 10, 0, tzinfo=IST).astimezone(timezone.utc)


def test_before_ten_the_window_started_yesterday():
    window = _window()
    start, end = local_day_bounds(window, datetime(2026, 5, 12, 9, 30, tzinfo=IST))
    assert start == datetime(2026, 5, 11, 10, 0, tzinfo=IST).astimezone(timezone.utc)
    assert end == datetime(2026, 5, 12, 10, 0, tzinfo=IST).astimezone(timezone.utc)


def test_the_window_always_contains_the_moment():
    window = _window()
    for hour in range(0, 24):
        moment = datetime(2026, 5, 12, hour, 17, tzinfo=IST)
        start, end = local_day_bounds(window, moment)
        assert start <= moment.astimezone(timezone.utc) < end


def test_the_reset_hour_is_configurable():
    window = _window()
    start, end = local_day_bounds(window, datetime(2026, 5, 12, 1, 0, tzinfo=IST), reset_hour=0)
    # With a midnight reset the window is the calendar day.
    assert start == datetime(2026, 5, 12, 0, 0, tzinfo=IST).astimezone(timezone.utc)
    assert end == datetime(2026, 5, 13, 0, 0, tzinfo=IST).astimezone(timezone.utc)


def test_quota_follows_the_users_own_timezone():
    """The same instant can be in different quota days for different users."""
    ist = _window("Asia/Kolkata")
    nyc = _window("America/New_York")

    moment = datetime(2026, 5, 12, 5, 0, tzinfo=timezone.utc)  # 10:30 IST, 01:00 NYC

    ist_start, _ = local_day_bounds(ist, moment)
    nyc_start, _ = local_day_bounds(nyc, moment)

    # 10:30 IST has just rolled over onto the 12th; 01:00 NYC is still on the 11th.
    assert ist_start == datetime(2026, 5, 12, 10, 0, tzinfo=ist.timezone).astimezone(timezone.utc)
    assert nyc_start == datetime(2026, 5, 11, 10, 0, tzinfo=nyc.timezone).astimezone(timezone.utc)
    assert ist_start != nyc_start


def test_an_unknown_timezone_does_not_silently_become_utc():
    window = resolve_window({"start": "09:00", "end": "21:00", "timezone": "Mars/Olympus"})
    assert window.timezone_name == settings.safety_default_timezone


def test_default_timezone_is_india():
    assert settings.safety_default_timezone == "Asia/Kolkata"
    window = resolve_window(None)
    assert window.timezone_name == "Asia/Kolkata"


# ------------------------------------------------------------------- the count


async def test_the_daily_cap_is_ten_by_default(db):
    user = await make_user(db, email="cap@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=10)
    snapshot = await usage_snapshot(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
    )
    assert snapshot.effective_daily_cap == 10
    assert snapshot.day_reset_hour == 10
    assert snapshot.quota_resets_at is not None


async def test_applications_made_now_count_against_the_current_window(db):
    from app.db.models import Application

    session = db
    user = await make_user(session, email="window@example.com")
    preferences = await make_preferences(session, user.id, daily_cap=10)

    session.add(
        Application(
            user_id=user.id,
            platform="linkedin",
            job_id="j1",
            status=ApplicationStatus.APPLIED.value,
            created_at=utcnow(),
        )
    )
    await session.commit()

    snapshot = await usage_snapshot(
        session,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
    )
    assert snapshot.applied_today == 1


async def test_dry_runs_count_against_the_quota(db):
    """A practice run still hits the platform, so it still counts."""
    from app.db.models import Application

    session = db
    user = await make_user(session, email="dry@example.com")
    preferences = await make_preferences(session, user.id, daily_cap=2)

    session.add(
        Application(
            user_id=user.id,
            platform="linkedin",
            job_id="j1",
            status=ApplicationStatus.DRY_RUN.value,
            created_at=utcnow(),
        )
    )
    await session.commit()

    snapshot = await usage_snapshot(
        session,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
    )
    assert snapshot.applied_today == 1


# ------------------------------------------------------- enforcement on submit


async def test_submit_is_blocked_once_the_daily_cap_is_reached(db):
    from app.db.models import Application

    user = await make_user(db, email="submit-cap@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=2)

    for index in range(2):
        db.add(
            Application(
                user_id=user.id,
                platform="linkedin",
                job_id=f"j{index}",
                status=ApplicationStatus.APPLIED.value,
                created_at=utcnow(),
            )
        )
    await db.commit()

    allowed, reason = await check_submit_allowed(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
    )
    assert allowed is False
    assert reason == PolicyReason.DAILY_CAP


async def test_submit_is_blocked_by_the_hourly_cap(db):
    from app.db.models import Application

    user = await make_user(db, email="submit-hourly@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=50)

    for index in range(3):
        db.add(
            Application(
                user_id=user.id,
                platform="linkedin",
                job_id=f"h{index}",
                status=ApplicationStatus.APPLIED.value,
                created_at=utcnow(),
            )
        )
    await db.commit()

    allowed, reason = await check_submit_allowed(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
    )
    assert allowed is False
    assert reason == PolicyReason.HOURLY_CAP


async def test_submit_is_allowed_under_the_cap(db):
    user = await make_user(db, email="submit-ok@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=10)

    allowed, reason = await check_submit_allowed(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
    )
    assert allowed is True
    assert reason == ""


async def test_submit_is_blocked_by_a_cooldown(db):
    from app.safety.policy import record_hard_stop

    user = await make_user(db, email="submit-cooldown@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=10)
    await record_hard_stop(
        db, user_id=user.id, run_id=None, event_type="captcha", cooldown_hours=24
    )

    allowed, reason = await check_submit_allowed(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
    )
    assert allowed is False
    assert reason == PolicyReason.COOLDOWN


async def test_the_server_blocks_the_submit_not_just_the_run(client_factory, db):
    """The end-to-end guarantee: the cap holds even with a healthy extension."""
    from sqlalchemy import select

    from app.db.models import Application, User

    alice = client_factory()
    await alice.post("/api/auth/dev-login", json={"email": "quota-e2e@example.com"})
    await complete_onboarding(alice)
    token = await connect_extension(alice, install_id="quota-e2e")

    run = await start_run(alice, token, dry_run=False)

    # Fill the daily allowance behind the scenes, as if earlier runs had used it.
    row = (
        await db.execute(select(User).where(User.email == "quota-e2e@example.com"))
    ).scalar_one()
    for index in range(10):
        db.add(
            Application(
                user_id=row.id,
                platform="linkedin",
                job_id=f"pre-{index}",
                status="applied",
                created_at=utcnow(),
            )
        )
    await db.commit()

    result = await agent_step(
        alice,
        token,
        observation(
            run_id=run["id"],
            page_type="apply_form",
            elements=[
                {"ref": "f1", "kind": "text", "label": "Full name", "required": True, "value": None},
                {"ref": "b1", "kind": "button", "label": "Submit application"},
            ],
        ),
    )

    # The submit is gone: the server refused it.
    assert all(action["type"] != "submit" for action in result["actions"])
    assert result["status"] == "done"
    assert result["reason"] == "cap_reached"

    ledger = (await alice.get("/api/applications?status=skipped")).json()["items"]
    assert any(item["reason"] == "cap_reached" for item in ledger)

    # And the run is over rather than looping on blocked applications.
    assert (await alice.get("/api/runs/active")).json()["run"] is None


async def test_the_daily_llm_budget_is_shared_across_runs(client_factory, db):
    """Many short runs must not mean unlimited model spend."""
    from app.db.models import AgentRun

    alice = client_factory()
    await alice.post("/api/auth/dev-login", json={"email": "llm-budget@example.com"})
    await complete_onboarding(alice)
    token = await connect_extension(alice, install_id="llm-budget")

    run = await start_run(alice, token, dry_run=False)

    from sqlalchemy import select

    stored = (
        await db.execute(
            select(AgentRun).where(AgentRun.id == uuid.UUID(run["id"]))
        )
    ).scalar_one()
    stored.llm_calls = settings.llm_max_calls_per_day + 5
    await db.commit()

    result = await agent_step(
        alice,
        token,
        observation(
            run_id=run["id"],
            page_type="chat_question",
            elements=[button("b9", "Next")],
            chat={
                "question": "Describe a time you disagreed with your manager.",
                "input_ref": "c1",
            },
        ),
    )

    # No budget left, so the question goes to a human instead of a model, and the
    # run's call counter does not move.
    assert result["status"] == "hitl"
    assert result["meta"]["llm_calls"] == settings.llm_max_calls_per_day + 5
    assert result["meta"]["llm_calls_left"] == 0


# ------------------------------------------------------------------- api shape


async def test_safety_status_reports_when_the_quota_resets(onboarded):
    body = (await onboarded.get("/api/safety/status")).json()

    assert body["usage"]["day_reset_hour"] == 10
    assert body["usage"]["quota_resets_at"] is not None
    assert body["usage"]["effective_daily_cap"] <= 10


async def test_start_run_reports_the_remaining_allowance(onboarded, extension_token):
    body = (
        await onboarded.post(
            "/api/runs/start",
            json={"platform": "linkedin", "dry_run": False},
            headers=extension_headers(extension_token),
        )
    ).json()

    assert body["usage"]["day_reset_hour"] == 10
    assert body["usage"]["effective_daily_cap"] <= 10
    assert body["run"]["max_applications"] <= 10


# --------------------------------------------------------------- the warm-up


async def test_a_new_account_ramps_up_to_ten(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 14)
    monkeypatch.setattr(settings, "safety_warmup_start_cap", 5)

    user = await make_user(db, email="warm@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=10)

    snapshot = await usage_snapshot(
        db, user_id=user.id, account_created_at=user.created_at, preferences=preferences
    )
    assert snapshot.effective_daily_cap == 5
    assert snapshot.warmup_cap == 5

    # A month later the account is at the full ten.
    old = utcnow() - timedelta(days=30)
    snapshot = await usage_snapshot(
        db, user_id=user.id, account_created_at=old, preferences=preferences
    )
    assert snapshot.effective_daily_cap == 10
