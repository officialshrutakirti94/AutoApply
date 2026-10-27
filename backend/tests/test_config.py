"""Configuration contract tests.

`.env.example` is the only setup document a new developer gets, so it must stay in
lockstep with the settings class. And the production guards must actually fire,
because "we'll notice at deploy" is not a plan.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def _documented_keys() -> set[str]:
    keys: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            keys.add(stripped.split("=", 1)[0].strip().lower())
    return keys


def test_env_example_documents_every_setting():
    missing = sorted(set(Settings.model_fields) - _documented_keys())
    assert not missing, f"settings missing from .env.example: {missing}"


def test_env_example_has_no_stale_settings():
    extra = sorted(_documented_keys() - set(Settings.model_fields))
    assert not extra, f".env.example documents settings that do not exist: {extra}"


def _production(**overrides) -> Settings:
    payload = {
        "app_env": "production",
        "secret_key": "a" * 48,
        "google_client_id": "1234.apps.googleusercontent.com",
        "cron_secret": "cron-secret",
        "auth_dev_bypass": False,
        "storage_backend": "local",
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)


def test_production_config_is_accepted_when_complete():
    settings = _production()
    assert settings.is_production is True
    assert settings.auto_create_schema is False


@pytest.mark.parametrize(
    "secret",
    ["", "change-me", "change-me-48-random-characters", "short"],
)
def test_production_rejects_a_weak_or_default_secret(secret):
    with pytest.raises(ValidationError):
        _production(secret_key=secret)


def test_production_rejects_the_dev_bypass():
    with pytest.raises(ValidationError):
        _production(auth_dev_bypass=True)


def test_production_requires_a_google_client_id():
    with pytest.raises(ValidationError):
        _production(google_client_id="")


def test_production_requires_a_cron_secret():
    with pytest.raises(ValidationError):
        _production(cron_secret="")


def test_production_requires_complete_s3_credentials():
    with pytest.raises(ValidationError):
        _production(storage_backend="s3", s3_bucket="bucket")


def test_production_accepts_a_complete_supabase_s3_config():
    settings = _production(
        storage_backend="s3",
        s3_endpoint_url="https://abcdefg.supabase.co/storage/v1/s3/",
        s3_region="ap-south-1",
        s3_access_key_id="key-id",
        s3_secret_access_key="secret",
        s3_bucket="autoapply-private",
    )
    # The trailing slash is stripped so URLs are built the same way everywhere.
    assert settings.s3_endpoint_url == "https://abcdefg.supabase.co/storage/v1/s3"


def test_development_allows_auto_created_schema():
    settings = Settings(_env_file=None, app_env="development")
    assert settings.auto_create_schema is True
    assert settings.is_production is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgresql://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("sqlite+aiosqlite://", "sqlite+aiosqlite://"),
    ],
)
def test_database_url_is_normalised_for_sqlalchemy(raw, expected):
    settings = Settings(_env_file=None, database_url=raw)
    assert settings.effective_database_url == expected


def test_neon_ssl_params_are_translated_for_asyncpg():
    """asyncpg has no `sslmode` kwarg; passing it through raises TypeError at connect."""
    settings = Settings(
        _env_file=None,
        database_url=(
            "postgresql://owner:pw@ep-x-pooler.c-7.us-east-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        ),
    )
    url = settings.effective_database_url

    assert url.startswith("postgresql+asyncpg://")
    assert "channel_binding" not in url
    assert "sslmode" not in url
    assert url.endswith("?ssl=require")


def test_database_url_keeps_params_asyncpg_understands():
    settings = Settings(
        _env_file=None,
        database_url="postgresql://u:p@host/db?ssl=require&application_name=autoapply",
    )
    url = settings.effective_database_url
    assert "ssl=require" in url
    # application_name is dropped: asyncpg takes it as a different kwarg.
    assert "application_name" not in url


def test_trailing_slashes_are_stripped_from_urls():
    settings = Settings(
        _env_file=None,
        backend_base_url="https://api.example.com/",
        dashboard_url="https://app.example.com/",
    )
    assert settings.backend_base_url == "https://api.example.com"
    assert settings.dashboard_url == "https://app.example.com"


def test_cors_origins_are_split_and_trimmed():
    settings = Settings(
        _env_file=None, cors_origins="http://localhost:5173, https://app.example.com ,"
    )
    assert settings.cors_origin_list == ["http://localhost:5173", "https://app.example.com"]


def test_log_level_is_normalised():
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"
