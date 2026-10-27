"""Plan entitlements.

The plan is the *entitlement*: the most the account may do in one quota day. The
user's own `daily_cap` preference can only lower it, and the hard ceilings in
`app/safety/policy.py` can only lower it further. Nothing here lets the LLM or the
client raise a limit.

Three tiers, deliberately close together. LinkedIn and Naukri do not care that
someone paid: the difference between Pro and Pro Plus is how much more risk their
account can absorb, so the top tier sits exactly on the hard daily ceiling (25)
rather than above it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.db.enums import PlanTier

DAILY_CEILING = 25
HOURLY_CEILING = 6


@dataclass(frozen=True, slots=True)
class PlanLimits:
    tier: str
    label: str
    daily_cap: int
    hourly_cap: int
    llm_calls_per_day: int
    price: str
    blurb: str

    def as_dict(self) -> dict:
        return asdict(self)


PLANS: dict[str, PlanLimits] = {
    PlanTier.REGULAR.value: PlanLimits(
        tier=PlanTier.REGULAR.value,
        label="Regular",
        daily_cap=10,
        hourly_cap=3,
        llm_calls_per_day=60,
        price="Free",
        blurb="10 applications a day, both platforms, everything the agent can do.",
    ),
    PlanTier.PRO.value: PlanLimits(
        tier=PlanTier.PRO.value,
        label="Pro",
        daily_cap=18,
        hourly_cap=4,
        llm_calls_per_day=120,
        price="₹499 / month",
        blurb="18 applications a day and more room for free-text screening answers.",
    ),
    PlanTier.PRO_PLUS.value: PlanLimits(
        tier=PlanTier.PRO_PLUS.value,
        label="Pro Plus",
        daily_cap=25,
        hourly_cap=6,
        llm_calls_per_day=200,
        price="₹999 / month",
        blurb="The maximum we allow. 25 applications a day, the hard safety ceiling.",
    ),
}

DEFAULT_PLAN = PlanTier.REGULAR.value


def limits_for(plan: str | None) -> PlanLimits:
    return PLANS.get(plan or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])


def catalogue() -> list[dict]:
    """Every tier, for the pricing section and the plan card."""
    return [limits.as_dict() for limits in PLANS.values()]
