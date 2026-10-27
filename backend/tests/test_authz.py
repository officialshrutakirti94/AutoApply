"""Authorization tests. These are release blockers, not nice-to-have coverage.

Each test answers one question: can this credential reach data it does not own?
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Application, User
from tests.helpers import (
    complete_onboarding,
    connect_extension,
    extension_headers,
    start_run,
)


async def _sign_in(client, email: str) -> None:
    response = await client.post("/api/auth/dev-login", json={"email": email})
    assert response.status_code == 200, response.text


async def test_users_only_see_their_own_applications(client_factory, db):
    alice, bob = client_factory(), client_factory()
    await _sign_in(alice, "alice@example.com")
    await _sign_in(bob, "bob@example.com")

    alice_user = (await db.execute(select(User).where(User.email == "alice@example.com"))).scalar_one()
    db.add(
        Application(
            user_id=alice_user.id,
            platform="linkedin",
            job_id="job-1",
            job_title="Backend Engineer",
            status="applied",
        )
    )
    await db.commit()

    alice_apps = (await alice.get("/api/applications")).json()["items"]
    bob_apps = (await bob.get("/api/applications")).json()["items"]

    assert len(alice_apps) == 1
    assert bob_apps == []

    # Bob knows the id and still cannot touch it.
    response = await bob.patch(
        f"/api/applications/{alice_apps[0]['id']}", json={"status": "resolved"}
    )
    assert response.status_code == 404


async def test_extension_token_cannot_read_profile(client_factory, onboarded):
    token = await connect_extension(onboarded, install_id="scope-read")

    # A cookie-less client: this is exactly what a leaked extension token gives you.
    bare = client_factory()
    response = await bare.get("/api/profile", headers=extension_headers(token))
    assert response.status_code == 401


async def test_extension_token_cannot_write_preferences(client_factory, onboarded):
    token = await connect_extension(onboarded, install_id="scope-write")

    bare = client_factory()
    response = await bare.put(
        "/api/preferences",
        json={"daily_cap": 25},
        headers=extension_headers(token),
    )
    assert response.status_code == 401


async def test_extension_token_cannot_list_extension_tokens(client_factory, onboarded):
    token = await connect_extension(onboarded, install_id="scope-list")

    bare = client_factory()
    response = await bare.get("/api/extension/tokens", headers=extension_headers(token))
    assert response.status_code == 401


async def test_extension_token_cannot_touch_another_users_run(client_factory):
    alice, bob = client_factory(), client_factory()
    await _sign_in(alice, "alice2@example.com")
    await _sign_in(bob, "bob2@example.com")
    await complete_onboarding(alice)
    await complete_onboarding(bob)

    alice_token = await connect_extension(alice, install_id="alice-install")
    bob_token = await connect_extension(bob, install_id="bob-install")

    run = await start_run(alice, alice_token)

    response = await bob.post(
        f"/api/runs/{run['id']}/heartbeat", headers=extension_headers(bob_token)
    )
    assert response.status_code == 404

    response = await bob.post(
        f"/api/runs/{run['id']}/stop", json={}, headers=extension_headers(bob_token)
    )
    assert response.status_code == 404


async def test_extension_token_cannot_post_another_users_observation(client_factory):
    alice, bob = client_factory(), client_factory()
    await _sign_in(alice, "alice3@example.com")
    await _sign_in(bob, "bob3@example.com")
    await complete_onboarding(alice)
    await complete_onboarding(bob)

    alice_token = await connect_extension(alice, install_id="alice-3")
    bob_token = await connect_extension(bob, install_id="bob-3")
    run = await start_run(alice, alice_token)

    response = await bob.post(
        "/api/agent/step",
        json={
            "run_id": run["id"],
            "platform": "linkedin",
            "page_type": "job_detail",
            "job": {"id": "1"},
            "elements": [],
        },
        headers=extension_headers(bob_token),
    )
    assert response.status_code == 404


async def test_revoked_extension_token_stops_working(onboarded, extension_token):
    tokens = (await onboarded.get("/api/extension/tokens")).json()
    assert len(tokens) == 1

    revoke = await onboarded.delete(f"/api/extension/tokens/{tokens[0]['id']}")
    assert revoke.status_code == 204

    response = await onboarded.post(
        "/api/platform/status",
        json={"platform": "linkedin", "signed_in": True},
        headers=extension_headers(extension_token),
    )
    assert response.status_code == 401


async def test_revoking_someone_elses_token_is_a_404(client_factory):
    alice, bob = client_factory(), client_factory()
    await _sign_in(alice, "alice4@example.com")
    await _sign_in(bob, "bob4@example.com")
    await complete_onboarding(alice)
    await complete_onboarding(bob)

    await connect_extension(alice, install_id="alice-4")
    alice_tokens = (await alice.get("/api/extension/tokens")).json()

    response = await bob.delete(f"/api/extension/tokens/{alice_tokens[0]['id']}")
    assert response.status_code == 404


async def test_garbage_bearer_token_is_rejected(onboarded):
    response = await onboarded.post(
        "/api/platform/status",
        json={"platform": "linkedin", "signed_in": True},
        headers={"Authorization": "Bearer aa_ext_not-a-real-token"},
    )
    assert response.status_code == 401


async def test_pairing_code_is_single_use(onboarded):
    pair = await onboarded.post("/api/extension/pair")
    code = pair.json()["code"]

    first = await onboarded.post("/api/extension/connect", json={"code": code})
    assert first.status_code == 200

    second = await onboarded.post("/api/extension/connect", json={"code": code})
    assert second.status_code == 401


async def test_pairing_code_is_normalised(onboarded):
    pair = await onboarded.post("/api/extension/pair")
    code = pair.json()["code"]
    spaced = f"{code[:4]} {code[4:]}".lower()

    response = await onboarded.post("/api/extension/connect", json={"code": spaced})
    assert response.status_code == 200


async def test_delete_account_removes_everything(client_factory, db):
    alice = client_factory()
    await _sign_in(alice, "delete-me@example.com")
    await complete_onboarding(alice)
    token = await connect_extension(alice, install_id="delete-install")
    await start_run(alice, token)

    user = (await db.execute(select(User).where(User.email == "delete-me@example.com"))).scalar_one()
    db.add(
        Application(user_id=user.id, platform="linkedin", job_id="x", status="applied")
    )
    await db.commit()

    response = await alice.delete("/api/account")
    assert response.status_code == 204

    assert (await alice.get("/api/auth/me")).status_code == 401

    remaining_user = (
        await db.execute(select(User).where(User.email == "delete-me@example.com"))
    ).scalar_one_or_none()
    assert remaining_user is None

    remaining_apps = (
        await db.execute(select(Application).where(Application.user_id == user.id))
    ).scalars().all()
    assert remaining_apps == []


async def test_expired_session_is_rejected(client_factory, db):
    from app.core.security import hash_secret
    from app.core.timeutils import utcnow
    from app.db.models import UserSession

    alice = client_factory()
    await _sign_in(alice, "expired@example.com")
    cookie = alice.cookies.get("aa_session")
    assert cookie

    session = (
        await db.execute(select(UserSession).where(UserSession.token_hash == hash_secret(cookie)))
    ).scalar_one()
    session.expires_at = utcnow().replace(year=utcnow().year - 1)
    await db.commit()

    assert (await alice.get("/api/auth/me")).status_code == 401
