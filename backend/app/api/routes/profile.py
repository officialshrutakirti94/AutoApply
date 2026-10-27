"""Profile, preferences and the onboarding gate."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter

from app.api.presenters import build_me, preference_out, profile_out
from app.api.schemas import (
    MeOut,
    OnboardingCompleteRequest,
    PreferenceOut,
    PreferenceUpdate,
    ProfileOut,
    ProfileUpdate,
)
from app.core.deps import CurrentUser, DbSession
from app.core.errors import Unprocessable
from app.core.timeutils import utcnow
from app.db.models import Preference, Profile

router = APIRouter(tags=["profile"])


async def get_or_create_profile(
    db: AsyncSession, *, user_id, email: str | None = None
) -> Profile:
    """Fetch the profile, creating it on first use.

    The dashboard fires several requests at once on a new account (the shell, the
    setup screen, the resume draft), so two of them can both find no row and both
    try to insert. The unique key then rejects the loser with an IntegrityError and
    the user sees a 500. Catching it and re-reading is the fix.
    """
    profile = await db.get(Profile, user_id)

    if profile is not None:
        if profile.email is None and email:
            # The account email is authoritative; the profile copy is for forms.
            profile.email = email
            await db.commit()
            await db.refresh(profile)
        return profile

    profile = Profile(user_id=user_id, email=email)
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError:
        # Lost the race: another request created it a moment ago.
        await db.rollback()
        existing = await db.get(Profile, user_id)
        if existing is None:
            raise
        return existing

    await db.refresh(profile)
    return profile


async def get_or_create_preferences(db: AsyncSession, *, user_id) -> Preference:
    """Same first-use race as the profile: insert, and re-read if we lost."""
    preference = await db.get(Preference, user_id)
    if preference is not None:
        return preference

    preference = Preference(user_id=user_id, active_hours={})
    db.add(preference)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.get(Preference, user_id)
        if existing is None:
            raise
        return existing

    await db.refresh(preference)
    return preference


@router.get("/profile", response_model=ProfileOut)
async def read_profile(user: CurrentUser, db: DbSession) -> ProfileOut:
    profile = await get_or_create_profile(db, user_id=user.id, email=user.email)
    return profile_out(profile)  # type: ignore[return-value]


@router.put("/profile", response_model=ProfileOut)
async def update_profile(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> ProfileOut:
    profile = await get_or_create_profile(db, user_id=user.id, email=user.email)
    changes = payload.model_dump(exclude_unset=True)

    if "education" in changes and changes["education"] is not None:
        changes["education"] = [
            item.model_dump() if hasattr(item, "model_dump") else item for item in payload.education or []
        ]

    for field, value in changes.items():
        if field == "onboarding_step" and value is not None:
            # Never move the rail backwards implicitly.
            profile.onboarding_step = max(profile.onboarding_step, value)
            continue
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return profile_out(profile)  # type: ignore[return-value]


@router.get("/preferences", response_model=PreferenceOut)
async def read_preferences(user: CurrentUser, db: DbSession) -> PreferenceOut:
    preference = await get_or_create_preferences(db, user_id=user.id)
    return preference_out(preference)


@router.put("/preferences", response_model=PreferenceOut)
async def update_preferences(
    payload: PreferenceUpdate, user: CurrentUser, db: DbSession
) -> PreferenceOut:
    preference = await get_or_create_preferences(db, user_id=user.id)
    changes = payload.model_dump(exclude_unset=True)

    if "active_hours" in changes and payload.active_hours is not None:
        hours = payload.active_hours
        if hours.start == hours.end:
            raise Unprocessable("Active hours cannot start and end at the same time.")
        changes["active_hours"] = hours.model_dump()

    for field, value in changes.items():
        setattr(preference, field, value)

    await db.commit()
    await db.refresh(preference)
    return preference_out(preference)


@router.post("/onboarding/complete", response_model=MeOut)
async def complete_onboarding(
    payload: OnboardingCompleteRequest, user: CurrentUser, db: DbSession
) -> MeOut:
    profile = await get_or_create_profile(db, user_id=user.id, email=user.email)
    preference = await get_or_create_preferences(db, user_id=user.id)

    missing: list[str] = []
    if not (profile.full_name or "").strip():
        missing.append("full name")
    if not (preference.target_roles or []):
        missing.append("at least one role")
    if not (preference.platforms or []):
        missing.append("at least one platform")
    if missing:
        raise Unprocessable(
            "A few things are still needed: " + ", ".join(missing) + ".",
            details=[{"field": item, "message": "required"} for item in missing],
        )

    if profile.risk_accepted_at is None:
        profile.risk_accepted_at = utcnow()
    profile.onboarding_done = True
    profile.onboarding_step = 7

    await db.commit()
    await db.refresh(profile)
    return await build_me(db, user)
