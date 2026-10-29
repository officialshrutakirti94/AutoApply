"""Request and response models for the HTTP API.

Two conventions worth knowing:

* Updates are partial: send only what changed, and send ``null`` to clear a field.
* Every user-owned model omits internal columns (hashes, keys, storage paths).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PlatformLiteral = Literal["linkedin", "naukri"]
WorkMode = Literal["remote", "hybrid", "onsite"]
ExperienceLevel = Literal["entry", "mid", "experienced"]

HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


# ------------------------------------------------------------------------ auth


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None = None
    avatar_url: str | None = None
    # regular | pro | pro_plus - see app/safety/plans.py
    plan: str = "regular"
    created_at: datetime


class OnboardingOut(BaseModel):
    step: int
    done: bool
    has_resume: bool
    parse_status: str
    needs_risk_consent: bool


class PlatformChip(BaseModel):
    platform: str
    signed_in: bool
    last_seen_at: datetime | None = None


class MeOut(BaseModel):
    user: UserOut
    onboarding: OnboardingOut
    platforms: list[PlatformChip] = Field(default_factory=list)
    preferences_ready: bool = False
    llm: dict[str, Any] = Field(default_factory=dict)


class GoogleSignInRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=8000)


class DevSignInRequest(BaseModel):
    email: str | None = Field(default=None, max_length=320)


# --------------------------------------------------------------------- profile


class EducationItem(BaseModel):
    degree: str | None = Field(default=None, max_length=200)
    institution: str | None = Field(default=None, max_length=200)
    year: str | None = Field(default=None, max_length=20)


class ProfileOut(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    naukri_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    other_links: list[str] = Field(default_factory=list)
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    years_of_experience: float | None = None
    current_title: str | None = None
    current_company: str | None = None
    education: list[EducationItem] = Field(default_factory=list)
    notice_period_days: int | None = None
    current_ctc_lpa: float | None = None
    expected_ctc_lpa: float | None = None
    work_authorization: str | None = None
    parse_status: str = "none"
    onboarding_step: int = 1
    onboarding_done: bool = False
    has_resume: bool = False


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=200)
    linkedin_url: str | None = Field(default=None, max_length=500)
    naukri_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    other_links: list[str] | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=4000)
    skills: list[str] | None = Field(default=None, max_length=60)
    years_of_experience: float | None = Field(default=None, ge=0, le=60)
    current_title: str | None = Field(default=None, max_length=200)
    current_company: str | None = Field(default=None, max_length=200)
    education: list[EducationItem] | None = Field(default=None, max_length=10)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    current_ctc_lpa: float | None = Field(default=None, ge=0, le=1000)
    expected_ctc_lpa: float | None = Field(default=None, ge=0, le=1000)
    work_authorization: str | None = Field(default=None, max_length=200)
    onboarding_step: int | None = Field(default=None, ge=1, le=7)


class ActiveHours(BaseModel):
    start: str = Field(default="09:00", pattern=HHMM_PATTERN)
    end: str = Field(default="21:00", pattern=HHMM_PATTERN)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)


class PreferenceOut(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    experience_level: str | None = None
    platforms: list[str] = Field(default_factory=list)
    active_hours: ActiveHours = Field(default_factory=ActiveHours)
    daily_cap: int = 10
    blacklist_companies: list[str] = Field(default_factory=list)
    blacklist_keywords: list[str] = Field(default_factory=list)


class PreferenceUpdate(BaseModel):
    target_roles: list[str] | None = Field(default=None, max_length=20)
    domains: list[str] | None = Field(default=None, max_length=20)
    locations: list[str] | None = Field(default=None, max_length=20)
    work_mode: list[WorkMode] | None = Field(default=None, max_length=3)
    experience_level: ExperienceLevel | None = None
    platforms: list[PlatformLiteral] | None = Field(default=None, max_length=2)
    active_hours: ActiveHours | None = None
    daily_cap: int | None = Field(default=None, ge=1, le=25)
    blacklist_companies: list[str] | None = Field(default=None, max_length=100)
    blacklist_keywords: list[str] | None = Field(default=None, max_length=100)

    @field_validator("target_roles", "domains", "locations")
    @classmethod
    def _strip_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        return list(dict.fromkeys(cleaned))[:20]


class OnboardingCompleteRequest(BaseModel):
    risk_accepted: bool

    @model_validator(mode="after")
    def _must_accept(self) -> OnboardingCompleteRequest:
        if not self.risk_accepted:
            raise ValueError("The risk notice has to be accepted before autopilot can run.")
        return self


# ---------------------------------------------------------------------- resume


class ResumeOut(BaseModel):
    parse_status: str
    message: str | None = None
    draft: dict[str, Any] | None = None
    confidence: dict[str, str] = Field(default_factory=dict)
    profile: ProfileOut | None = None


# -------------------------------------------------------------------------- qa


class QaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_pattern: str
    answer: str
    source: str
    approved: bool
    sensitive: bool
    times_used: int
    created_at: datetime
    updated_at: datetime


class QaCreate(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)
    sensitive: bool = False


class QaUpdate(BaseModel):
    answer: str | None = Field(default=None, min_length=1, max_length=2000)
    approved: bool | None = None
    sensitive: bool | None = None


# ------------------------------------------------------------------- extension


class PairCodeOut(BaseModel):
    code: str
    expires_at: datetime
    instructions: str


class ExtensionConnectRequest(BaseModel):
    code: str = Field(min_length=4, max_length=20)
    install_id: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default=None, max_length=120)


class ExtensionConnectOut(BaseModel):
    token: str
    user_email: str
    user_name: str | None = None


class ExtensionTokenOut(BaseModel):
    id: uuid.UUID
    label: str | None = None
    install_id: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    active: bool


class PlatformStatusRequest(BaseModel):
    platform: PlatformLiteral
    signed_in: bool


class ResumeFileOut(BaseModel):
    url: str
    expires_in: int


# ----------------------------------------------------------------------- runs


class StartRunRequest(BaseModel):
    platform: PlatformLiteral
    dry_run: Literal[False] = False


class RunOut(BaseModel):
    id: uuid.UUID
    platform: str
    status: str
    dry_run: bool
    started_at: datetime
    ended_at: datetime | None = None
    last_heartbeat_at: datetime
    window_end: datetime
    max_applications: int
    applied_count: int
    skipped_count: int
    stuck_count: int
    llm_calls: int
    stop_reason: str | None = None


class SearchPlanOut(BaseModel):
    """What the run should search for.

    The extension token cannot read /preferences (dashboard scope), so the run
    response carries the query the browser needs: roles, locations and work modes.
    Building the platform URL stays in the platform adapter.
    """

    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    remote_first: bool = False


class StartRunOut(BaseModel):
    run: RunOut
    pacing: dict[str, Any]
    heartbeat_seconds: int
    keep_tab_visible: bool = True
    usage: dict[str, Any] | None = None
    search: SearchPlanOut = Field(default_factory=SearchPlanOut)


class HeartbeatOut(BaseModel):
    run: RunOut
    allowed: bool
    message: str
    reason: str | None = None
    cooldown_until: datetime | None = None


class StopRunRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=60)


class ActiveRunOut(BaseModel):
    run: RunOut | None = None
    today: dict[str, int] = Field(default_factory=dict)
    unresolved: int = 0
    heartbeat_seconds: int = 20


class AgentStepMeta(BaseModel):
    run_id: uuid.UUID
    run_status: str
    job_status: str | None = None
    applied_count: int = 0
    skipped_count: int = 0
    stuck_count: int = 0
    llm_calls: int = 0
    llm_calls_left: int = 0
    trace_id: str | None = None
    pacing: dict[str, Any] | None = None


# --------------------------------------------------------------- applications


class ApplicationOut(BaseModel):
    id: uuid.UUID
    platform: str
    job_id: str
    job_title: str | None = None
    company: str | None = None
    location: str | None = None
    job_url: str | None = None
    status: str
    reason: str | None = None
    reason_label: str | None = None
    has_screenshot: bool = False
    answers_used: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ApplicationListOut(BaseModel):
    items: list[ApplicationOut]
    total_unresolved: int = 0


class ApplicationResolveRequest(BaseModel):
    status: Literal["resolved", "skipped"] = "resolved"
    reason: str | None = Field(default=None, max_length=40)


class ScreenshotUrlOut(BaseModel):
    url: str
    expires_in: int


# --------------------------------------------------------------------- safety


class PlanLimitsOut(BaseModel):
    tier: str
    label: str
    daily_cap: int
    hourly_cap: int
    llm_calls_per_day: int
    price: str
    blurb: str


class PlanOut(BaseModel):
    plan: str
    label: str
    limits: PlanLimitsOut
    usage: dict[str, Any] = Field(default_factory=dict)
    available: list[PlanLimitsOut] = Field(default_factory=list)


class PlanSwitchRequest(BaseModel):
    plan: Literal["regular", "pro", "pro_plus"]


class SafetyStatusOut(BaseModel):
    allowed: bool
    message: str
    reason: str | None = None
    cooldown_until: datetime | None = None
    usage: dict[str, Any] | None = None
    daily_ceilings: dict[str, int] = Field(default_factory=dict)


class HealthOut(BaseModel):
    status: str
    database: str
    version: str
    env: str
    llm: dict[str, Any] = Field(default_factory=dict)
