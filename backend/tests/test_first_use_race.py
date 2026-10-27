"""First-use races.

On a brand-new account the dashboard fires several requests at once: the shell, the
setup screen, the resume draft. Each of those calls `get_or_create_profile`, so two
of them can both find no row and both try to insert. Before this test existed the
loser crashed with an IntegrityError and the user saw a 500 on /api/resume/draft.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.api.routes.profile import get_or_create_preferences, get_or_create_profile
from app.db.models import Preference, Profile, User


async def _user(session_factory, email: str) -> User:
    async with session_factory() as session:
        user = User(google_sub=f"dev:{email}", email=email, email_verified=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_concurrent_profile_creation_does_not_raise(session_factory):
    user = await _user(session_factory, "race-profile@example.com")

    async def create():
        async with session_factory() as session:
            return await get_or_create_profile(
                session, user_id=user.id, email="race-profile@example.com"
            )

    results = await asyncio.gather(create(), create(), create(), return_exceptions=True)

    errors = [item for item in results if isinstance(item, BaseException)]
    assert not errors, f"concurrent creation raised: {errors}"
    assert all(result.user_id == user.id for result in results)

    async with session_factory() as session:
        rows = (
            await session.execute(select(Profile).where(Profile.user_id == user.id))
        ).scalars().all()
    assert len(rows) == 1, "exactly one profile row must exist"


async def test_concurrent_preferences_creation_does_not_raise(session_factory):
    user = await _user(session_factory, "race-prefs@example.com")

    async def create():
        async with session_factory() as session:
            return await get_or_create_preferences(session, user_id=user.id)

    results = await asyncio.gather(create(), create(), create(), return_exceptions=True)

    errors = [item for item in results if isinstance(item, BaseException)]
    assert not errors, f"concurrent creation raised: {errors}"

    async with session_factory() as session:
        rows = (
            await session.execute(select(Preference).where(Preference.user_id == user.id))
        ).scalars().all()
    assert len(rows) == 1


async def test_a_second_call_returns_the_same_row(db):
    user = User(google_sub="dev:2nd@example.com", email="2nd@example.com", email_verified=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    first = await get_or_create_profile(db, user_id=user.id, email="2nd@example.com")
    second = await get_or_create_profile(db, user_id=user.id, email="2nd@example.com")

    assert first.user_id == second.user_id
    assert first.created_at == second.created_at


async def test_the_account_email_is_copied_onto_a_bare_profile(db):
    user = User(google_sub="dev:bare@example.com", email="bare@example.com", email_verified=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    profile = await get_or_create_profile(db, user_id=user.id, email=None)
    assert profile.email is None

    profile = await get_or_create_profile(db, user_id=user.id, email="bare@example.com")
    assert profile.email == "bare@example.com"


@pytest.mark.parametrize("path", ["/api/profile", "/api/resume/draft"])
async def test_a_brand_new_account_never_500s_on_first_contact(client, path):
    await client.post("/api/auth/dev-login", json={"email": "fresh-race@example.com"})

    # Both endpoints create the profile on demand; neither may blow up.
    first, second = await asyncio.gather(
        client.get("/api/profile"), client.get("/api/resume/draft")
    )
    assert first.status_code == 200
    assert second.status_code in {200, 404}
    assert (await client.get(path)).status_code in {200, 404}
