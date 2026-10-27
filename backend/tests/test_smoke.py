"""Smoke tests: the app boots, signs in, and the onboarding gate works."""

from __future__ import annotations

from tests.helpers import complete_onboarding


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["version"]


async def test_me_requires_a_session(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


async def test_dev_login_creates_a_session(signed_in):
    response = await signed_in.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "dev@example.com"
    assert body["onboarding"]["done"] is False
    assert body["onboarding"]["step"] == 1


async def test_csrf_header_is_required_for_writes(signed_in):
    response = await signed_in.put(
        "/api/profile", json={"full_name": "No Header"}, headers={"X-Requested-With": ""}
    )
    assert response.status_code == 403


async def test_onboarding_completion_gate(onboarded):
    response = await onboarded.get("/api/auth/me")
    body = response.json()
    assert body["onboarding"]["done"] is True
    assert body["onboarding"]["needs_risk_consent"] is False
    assert body["preferences_ready"] is True


async def test_onboarding_requires_risk_acceptance(signed_in):
    response = await signed_in.post("/api/onboarding/complete", json={"risk_accepted": False})
    assert response.status_code == 422


async def test_onboarding_requires_roles_and_platforms(signed_in):
    await signed_in.put("/api/profile", json={"full_name": "Someone"})
    response = await signed_in.post("/api/onboarding/complete", json={"risk_accepted": True})
    assert response.status_code == 422
    assert "role" in response.json()["error"]["message"]


async def test_logout_revokes_the_session(signed_in):
    assert (await signed_in.get("/api/auth/me")).status_code == 200
    assert (await signed_in.post("/api/auth/logout")).status_code == 204
    assert (await signed_in.get("/api/auth/me")).status_code == 401


async def test_health_does_not_leak_secrets(client):
    body = (await client.get("/health")).json()
    assert "secret" not in str(body).lower()
    assert "postgres" not in str(body).lower()


async def test_full_onboarding_via_api(signed_in):
    await complete_onboarding(signed_in)
    profile = (await signed_in.get("/api/profile")).json()
    assert profile["full_name"] == "Priya Sharma"
    assert profile["notice_period_days"] == 60

    preferences = (await signed_in.get("/api/preferences")).json()
    assert "Backend Engineer" in preferences["target_roles"]
    assert preferences["daily_cap"] == 10
