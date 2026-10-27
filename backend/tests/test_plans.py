"""Plan entitlements: regular / pro / pro plus.

The plan is an entitlement, not a suggestion. These tests pin the three tiers, prove
that a plan can never exceed the hard safety ceilings, and cover the demo-only switch
endpoint.
"""

from __future__ import annotations


from app.core.config import settings
from app.safety import plans
from app.safety.policy import HARD_DAILY_CEILING, HARD_HOURLY_CEILING, usage_snapshot
from tests.helpers import make_preferences, make_user


# ------------------------------------------------------------------ the table


def test_the_three_tiers_and_their_limits():
    assert plans.limits_for("regular").as_dict() | {} == {
        "tier": "regular",
        "label": "Regular",
        "daily_cap": 10,
        "hourly_cap": 3,
        "llm_calls_per_day": 60,
        "price": "Free",
        "blurb": plans.limits_for("regular").blurb,
    }
    assert plans.limits_for("pro").daily_cap == 18
    assert plans.limits_for("pro_plus").daily_cap == 25


def test_no_tier_exceeds_the_hard_ceilings():
    for tier in plans.PLANS.values():
        assert tier.daily_cap <= HARD_DAILY_CEILING, tier.tier
        assert tier.hourly_cap <= HARD_HOURLY_CEILING, tier.tier


def test_an_unknown_or_missing_plan_falls_back_to_regular():
    assert plans.limits_for(None).tier == "regular"
    assert plans.limits_for("enterprise").tier == "regular"
    assert plans.limits_for("").tier == "regular"


def test_the_catalogue_lists_every_tier_in_order():
    catalogue = plans.catalogue()
    assert [item["tier"] for item in catalogue] == ["regular", "pro", "pro_plus"]


# ------------------------------------------------------------- the entitlement


async def test_each_plan_raises_the_entitlement(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 0)  # ignore the ramp
    user = await make_user(db, email="tiers@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=10)

    for tier, expected in (("regular", 10), ("pro", 18), ("pro_plus", 25)):
        preferences.daily_cap = expected
        await db.commit()

        snapshot = await usage_snapshot(
            db,
            user_id=user.id,
            account_created_at=user.created_at,
            preferences=preferences,
            plan=tier,
        )
        assert snapshot.plan_daily_cap == expected
        assert snapshot.effective_daily_cap == expected


async def test_a_user_can_lower_their_own_cap_below_the_plan(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 0)
    user = await make_user(db, email="lower@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=4)

    snapshot = await usage_snapshot(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
        plan="pro_plus",
    )
    assert snapshot.effective_daily_cap == 4


async def test_a_user_cannot_raise_their_cap_above_the_plan(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 0)
    user = await make_user(db, email="raise@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=25)

    snapshot = await usage_snapshot(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
        plan="regular",
    )
    assert snapshot.effective_daily_cap == 10


async def test_a_stricter_deployment_ceiling_wins(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 0)
    monkeypatch.setattr(settings, "safety_daily_cap", 8)

    user = await make_user(db, email="ceiling@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=18)

    snapshot = await usage_snapshot(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
        plan="pro",
    )
    assert snapshot.effective_daily_cap == 8


async def test_the_warmup_ramp_still_applies_on_a_paid_plan(db, monkeypatch):
    monkeypatch.setattr(settings, "safety_warmup_days", 14)
    monkeypatch.setattr(settings, "safety_warmup_start_cap", 5)

    user = await make_user(db, email="warm-pro@example.com")
    preferences = await make_preferences(db, user.id, daily_cap=18)

    snapshot = await usage_snapshot(
        db,
        user_id=user.id,
        account_created_at=user.created_at,
        preferences=preferences,
        plan="pro",
    )
    assert snapshot.plan_daily_cap == 18
    assert snapshot.effective_daily_cap == 5


# -------------------------------------------------------------------- the API


async def test_me_carries_the_plan(signed_in):
    body = (await signed_in.get("/api/auth/me")).json()
    assert body["user"]["plan"] == "regular"


async def test_read_plan_lists_the_tiers_and_todays_usage(signed_in):
    body = (await signed_in.get("/api/plan")).json()

    assert body["plan"] == "regular"
    assert body["limits"]["daily_cap"] == 10
    assert [tier["tier"] for tier in body["available"]] == ["regular", "pro", "pro_plus"]
    assert body["usage"]["plan_label"] == "Regular"
    assert "quota_resets_at" in body["usage"]


async def test_switching_plan_moves_the_cap_with_it(signed_in):
    # Onboarding is what creates the preferences row the switch updates.
    await signed_in.put(
        "/api/preferences",
        json={"daily_cap": 10, "target_roles": ["Backend Engineer"], "platforms": ["linkedin"]},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    switched = await signed_in.post("/api/plan/switch", json={"plan": "pro"})
    assert switched.status_code == 200
    assert switched.json()["plan"] == "pro"
    assert switched.json()["limits"]["daily_cap"] == 18

    preferences = (await signed_in.get("/api/preferences")).json()
    assert preferences["daily_cap"] == 18

    usage = (await signed_in.get("/api/safety/status")).json()["usage"]
    assert usage["plan"] == "pro"
    assert usage["plan_daily_cap"] == 18


async def test_switching_plan_respects_a_customised_cap(signed_in):
    await signed_in.put("/api/preferences", json={"daily_cap": 4}, headers={"X-Requested-With": "XMLHttpRequest"})

    switched = await signed_in.post("/api/plan/switch", json={"plan": "pro_plus"})
    assert switched.status_code == 200

    preferences = (await signed_in.get("/api/preferences")).json()
    assert preferences["daily_cap"] == 4, "a deliberate lower cap must survive an upgrade"


async def test_switching_to_an_unknown_plan_is_rejected(signed_in):
    response = await signed_in.post("/api/plan/switch", json={"plan": "enterprise"})
    assert response.status_code == 422


async def test_the_switch_is_disabled_in_production(signed_in, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    response = await signed_in.post("/api/plan/switch", json={"plan": "pro"})
    assert response.status_code == 404


async def test_pro_plus_sits_exactly_on_the_hard_ceiling(signed_in):
    await signed_in.post("/api/plan/switch", json={"plan": "pro_plus"})
    body = (await signed_in.get("/api/plan")).json()
    assert body["limits"]["daily_cap"] == HARD_DAILY_CEILING
    assert body["limits"]["hourly_cap"] == HARD_HOURLY_CEILING
