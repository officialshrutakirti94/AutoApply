"""Application settings.

Every value comes from the environment (see ``.env.example``). Nothing secret has
a working production default: ``validate_for_runtime`` refuses to boot production
with placeholder credentials, which is cheaper than discovering it at first login.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRETS = {
    "",
    "change-me",
    "change-me-48-random-characters",
    "dev-only-insecure-secret-change-me",
}

# libpq parameters that asyncpg does not accept and that we translate or drop.
_LIBPQ_ONLY_PARAMS = {
    "sslmode",
    "channel_binding",
    "connect_timeout",
    "application_name",
    "target_session_attrs",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app -----------------------------------------------------------------
    app_env: Literal["development", "production", "test"] = "development"
    app_name: str = "AutoApply"
    api_prefix: str = "/api"
    backend_base_url: str = "http://localhost:8000"
    dashboard_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    secret_key: str = "dev-only-insecure-secret-change-me"
    cors_origins: str = "http://localhost:5173"

    # --- auth ----------------------------------------------------------------
    google_client_id: str = ""
    # Additional client IDs whose ID tokens are also accepted, comma separated.
    # Needed only if a second client is ever added (for example an extension
    # client using chrome.identity). Multiple clients are fine as long as they
    # live in the same Google Cloud project.
    google_extra_client_ids: str = ""
    google_client_secret: str = ""
    auth_dev_bypass: bool = False
    auth_dev_bypass_email: str = "dev@example.com"
    session_ttl_days: int = 30

    # --- database ------------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./.data/dev.db"
    database_url_unpooled: str = ""
    db_pool_size: int = 5
    db_echo: bool = False

    # --- storage -------------------------------------------------------------
    # "local" writes under STORAGE_LOCAL_DIR.
    # "supabase" uses the Supabase Storage REST API (URL + secret key) - the
    #            easiest path, because the project API keys already work.
    # "s3" talks the S3 protocol to any compatible provider, which needs a
    #      separate S3 access key pair generated in the Supabase dashboard.
    storage_backend: Literal["local", "supabase", "s3"] = "local"
    storage_local_dir: str = "./.data"

    supabase_url: str = ""
    supabase_secret_key: str = ""
    supabase_bucket: str = "autoapply-private"
    supabase_auto_create_bucket: bool = True

    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""
    signed_url_ttl_seconds: int = 300

    # --- llm -----------------------------------------------------------------
    llm_enabled: bool = False
    groq_api_key: str = ""
    groq_model_fast: str = "llama-3.3-70b-versatile"
    groq_model_small: str = "llama-3.1-8b-instant"
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    llm_max_calls_per_run: int = 30
    # Deployment ceiling across one quota day. The plan sets the real number
    # (regular 60, pro 120, pro plus 200); this can only lower it.
    llm_max_calls_per_day: int = 200
    llm_timeout_seconds: float = 20.0
    llm_max_retries: int = 2

    # --- tracing -------------------------------------------------------------
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "autoapply"

    # --- safety --------------------------------------------------------------
    # These two are DEPLOYMENT CEILINGS, not per-user limits. The plan decides the
    # actual number (regular 10, pro 18, pro plus 25 - see app/safety/plans.py);
    # these values can only lower it further. They default to the hard ceilings so
    # that plans, not configuration, set the real limits.
    safety_daily_cap: int = 25
    safety_hourly_cap: int = 6
    safety_warmup_days: int = 14
    safety_warmup_start_cap: int = 5
    # The quota day rolls over at this local hour, not at midnight: a day's
    # allowance starts in the morning and is spent during the working day.
    safety_day_reset_hour: int = 10
    # Timezone used when a user has not chosen one. LinkedIn and Naukri are
    # primarily an Indian market, so IST is the sane default; each user can
    # change it in Settings.
    safety_default_timezone: str = "Asia/Kolkata"
    safety_action_delay_min_ms: int = 400
    safety_action_delay_max_ms: int = 1800
    safety_apply_pause_min_s: int = 45
    safety_apply_pause_max_s: int = 180
    safety_long_break_every_n: int = 8
    safety_long_break_min_s: int = 240
    safety_long_break_max_s: int = 600
    safety_cooldown_hours: int = 24
    safety_heartbeat_seconds: int = 20
    safety_heartbeat_timeout_seconds: int = 180
    safety_run_window_minutes: int = 120
    safety_max_run_applications: int = 15
    safety_default_active_hours: str = "09:00-21:00"
    safety_rest_day: int = 6

    # --- ops -----------------------------------------------------------------
    upload_max_mb: int = 5
    screenshot_retention_days: int = 14
    session_sweep_interval_minutes: int = 60
    cron_secret: str = ""
    sentry_dsn: str = ""

    @field_validator("backend_base_url", "dashboard_url")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("s3_endpoint_url", "supabase_url")
    @classmethod
    def _strip_endpoint_slash(cls, value: str) -> str:
        return value.rstrip("/") if value else value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def auto_create_schema(self) -> bool:
        """Create tables from metadata outside production.

        Production must go through Alembic so schema drift is visible in review.
        """
        return self.app_env in {"development", "test"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def google_client_id_list(self) -> list[str]:
        """Every client ID whose ID tokens this backend will accept.

        One Web client for the dashboard is enough: the extension authenticates
        with a pairing code and never talks to Google. Extra IDs are supported so
        adding a second client later does not break sign-in, and a token minted
        for one of them cannot be replayed against another project.
        """
        ids: list[str] = []
        for raw in (self.google_client_id, self.google_extra_client_ids):
            for candidate in raw.split(","):
                candidate = candidate.strip()
                if candidate and candidate not in ids:
                    ids.append(candidate)
        return ids

    @property
    def effective_database_url(self) -> str:
        """Normalise the URL a host hands out into something asyncpg accepts.

        Neon gives a libpq-style URL (``?sslmode=require&channel_binding=require``).
        SQLAlchemy passes unknown query keys straight to ``asyncpg.connect()``,
        which has no ``sslmode`` argument and raises ``TypeError`` at connect
        time. So: force the asyncpg driver, map ``sslmode`` onto asyncpg's
        ``ssl`` parameter, and drop the libpq-only keys.
        """
        url = self.database_url.strip()
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url[len(prefix) :]
                break

        if not url.startswith("postgresql+asyncpg://"):
            return url

        parts = urlsplit(url)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        sslmode = next((value for key, value in pairs if key == "sslmode"), None)
        kept = [(key, value) for key, value in pairs if key not in _LIBPQ_ONLY_PARAMS]
        if sslmode and not any(key == "ssl" for key, _ in kept):
            kept.append(("ssl", sslmode))

        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)
        )

    @property
    def tests_use_sqlite(self) -> bool:
        return self.effective_database_url.startswith("sqlite")

    @model_validator(mode="after")
    def validate_for_runtime(self) -> Settings:
        if self.app_env == "production":
            if self.secret_key in INSECURE_SECRETS or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be a unique value of at least 32 characters in production")
            if not self.google_client_id:
                raise ValueError("GOOGLE_CLIENT_ID is required in production")
            if self.auth_dev_bypass:
                raise ValueError("AUTH_DEV_BYPASS must be false in production")
            if not self.cron_secret:
                raise ValueError("CRON_SECRET is required in production")
            if self.storage_backend == "supabase":
                if not self.supabase_url or not self.supabase_secret_key:
                    raise ValueError(
                        "Supabase storage is selected but SUPABASE_URL or SUPABASE_SECRET_KEY is missing"
                    )
                if not self.supabase_bucket:
                    raise ValueError("Supabase storage is selected but SUPABASE_BUCKET is empty")
            if self.storage_backend == "s3" and not all(
                [
                    self.s3_endpoint_url,
                    self.s3_region,
                    self.s3_access_key_id,
                    self.s3_secret_access_key,
                    self.s3_bucket,
                ]
            ):
                raise ValueError("S3 storage is selected but the S3 settings are incomplete")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
