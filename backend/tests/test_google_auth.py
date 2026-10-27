"""Google audience handling.

One Web client ID is enough for the whole product: the extension authenticates with
a pairing code and never contacts Google. These tests pin that down, and prove that
adding a second client later will not silently break sign-in.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings, settings
from app.core.errors import InvalidCredentials
from app.services import google as google_service

DASHBOARD_ID = "111111111111-dashboard.apps.googleusercontent.com"
EXTENSION_ID = "222222222222-extension.apps.googleusercontent.com"
A_TOKEN = "a-token-value-long-enough-to-pass-the-minimum"


# ------------------------------------------------------------------ the config


def test_a_single_client_id_is_the_default():
    settings = Settings(_env_file=None, google_client_id=DASHBOARD_ID)
    assert settings.google_client_id_list == [DASHBOARD_ID]


def test_extra_client_ids_are_merged_and_deduplicated():
    settings = Settings(
        _env_file=None,
        google_client_id=DASHBOARD_ID,
        google_extra_client_ids=f" {EXTENSION_ID} , {DASHBOARD_ID} ,",
    )
    assert settings.google_client_id_list == [DASHBOARD_ID, EXTENSION_ID]


def test_an_empty_config_accepts_nothing():
    assert Settings(_env_file=None).google_client_id_list == []


def test_whitespace_only_values_are_ignored():
    settings = Settings(
        _env_file=None, google_client_id=DASHBOARD_ID, google_extra_client_ids=" , ,  "
    )
    assert settings.google_client_id_list == [DASHBOARD_ID]


# --------------------------------------------------------------- verification


def _claims(**overrides) -> dict:
    payload = {
        "sub": "google-sub-1",
        "email": "User@Example.com",
        "email_verified": True,
        "name": "A User",
        "picture": "https://example.com/p.png",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("with_extension_client", [False, True])
def test_every_allowed_audience_is_passed_to_the_verifier(monkeypatch, with_extension_client):
    """A token minted for either client must be accepted."""
    monkeypatch.setattr(settings, "google_client_id", DASHBOARD_ID)
    monkeypatch.setattr(
        settings, "google_extra_client_ids", EXTENSION_ID if with_extension_client else ""
    )

    seen: dict = {}

    def fake_verify(credential, request, audience=None):
        seen["credential"] = credential
        seen["audience"] = audience
        return _claims()

    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", fake_verify)

    identity = asyncio.run(google_service.verify_google_id_token(A_TOKEN))

    expected = [DASHBOARD_ID] + ([EXTENSION_ID] if with_extension_client else [])
    assert seen["audience"] == expected
    assert seen["credential"] == A_TOKEN
    assert identity.subject == "google-sub-1"
    assert identity.email == "user@example.com"  # normalised to lowercase
    assert identity.email_verified is True


async def test_a_rejected_token_is_a_clear_auth_error(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", DASHBOARD_ID)

    def explode(*args, **kwargs):
        raise ValueError("Token has wrong audience")

    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", explode)

    with pytest.raises(InvalidCredentials):
        await google_service.verify_google_id_token(A_TOKEN)


async def test_an_unconfigured_server_says_so(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_extra_client_ids", "")

    with pytest.raises(InvalidCredentials, match="not configured"):
        await google_service.verify_google_id_token(A_TOKEN)


async def test_a_token_without_an_email_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", DASHBOARD_ID)
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *args, **kwargs: _claims(email="", email_verified=False),
    )

    with pytest.raises(InvalidCredentials, match="email"):
        await google_service.verify_google_id_token(A_TOKEN)


async def test_an_unverified_email_is_recorded_as_unverified(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", DASHBOARD_ID)
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *args, **kwargs: _claims(email_verified=False),
    )

    identity = await google_service.verify_google_id_token(A_TOKEN)
    assert identity.email_verified is False
