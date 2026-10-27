"""ORM -> response model conversion.

Kept in one module so the shape the dashboard receives is defined once. Nothing
here can leak a hash, a storage key or another user's row: every function takes
data that was already scoped to the caller.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ActiveHours,
    ApplicationOut,
    ExtensionTokenOut,
    MeOut,
    OnboardingOut,
    PlatformChip,
    PreferenceOut,
    ProfileOut,
    RunOut,
    UserOut,
)
from app.agents.llm import provider_status
from app.db.models import (
    AgentRun,
    Application,
    ExtensionToken,
    PlatformConnection,
    Preference,
    Profile,
    User,
)
from app.services.applications import REASON_LABELS


def user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def profile_out(profile: Profile | None) -> ProfileOut | None:
    if profile is None:
        return None
    return ProfileOut(
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        location=profile.location,
        linkedin_url=profile.linkedin_url,
        naukri_url=profile.naukri_url,
        github_url=profile.github_url,
        portfolio_url=profile.portfolio_url,
        other_links=list(profile.other_links or []),
        summary=profile.summary,
        skills=list(profile.skills or []),
        years_of_experience=(
            float(profile.years_of_experience) if profile.years_of_experience is not None else None
        ),
        current_title=profile.current_title,
        current_company=profile.current_company,
        education=list(profile.education or []),
        notice_period_days=profile.notice_period_days,
        current_ctc_lpa=(
            float(profile.current_ctc_lpa) if profile.current_ctc_lpa is not None else None
        ),
        expected_ctc_lpa=(
            float(profile.expected_ctc_lpa) if profile.expected_ctc_lpa is not None else None
        ),
        work_authorization=profile.work_authorization,
        parse_status=profile.parse_status,
        onboarding_step=profile.onboarding_step,
        onboarding_done=profile.onboarding_done,
        has_resume=bool(profile.resume_file_key),
    )


def preference_out(preference: Preference | None) -> PreferenceOut:
    if preference is None:
        return PreferenceOut()
    hours = preference.active_hours or {}
    return PreferenceOut(
        target_roles=list(preference.target_roles or []),
        domains=list(preference.domains or []),
        locations=list(preference.locations or []),
        work_mode=list(preference.work_mode or []),
        experience_level=preference.experience_level,
        platforms=list(preference.platforms or []),
        active_hours=ActiveHours(
            start=str(hours.get("start") or "09:00"),
            end=str(hours.get("end") or "21:00"),
            timezone=str(hours.get("timezone") or "Asia/Kolkata"),
        ),
        daily_cap=preference.daily_cap,
        blacklist_companies=list(preference.blacklist_companies or []),
        blacklist_keywords=list(preference.blacklist_keywords or []),
    )


def run_out(run: AgentRun) -> RunOut:
    return RunOut(
        id=run.id,
        platform=run.platform,
        status=run.status,
        dry_run=run.dry_run,
        started_at=run.started_at,
        ended_at=run.ended_at,
        last_heartbeat_at=run.last_heartbeat_at,
        window_end=run.window_end,
        max_applications=run.max_applications,
        applied_count=run.applied_count,
        skipped_count=run.skipped_count,
        stuck_count=run.stuck_count,
        llm_calls=run.llm_calls,
        stop_reason=run.stop_reason,
    )


def application_out(application: Application) -> ApplicationOut:
    return ApplicationOut(
        id=application.id,
        platform=application.platform,
        job_id=application.job_id,
        job_title=application.job_title,
        company=application.company,
        location=application.location,
        job_url=application.job_url,
        status=application.status,
        reason=application.reason,
        reason_label=REASON_LABELS.get(application.reason or ""),
        has_screenshot=bool(application.screenshot_key),
        answers_used=dict(application.answers_used or {}),
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def token_out(token: ExtensionToken) -> ExtensionTokenOut:
    return ExtensionTokenOut(
        id=token.id,
        label=token.label,
        install_id=token.install_id,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
        active=token.revoked_at is None,
    )


async def platform_chips(db: AsyncSession, *, user_id) -> list[PlatformChip]:
    rows = await db.execute(
        select(PlatformConnection).where(PlatformConnection.user_id == user_id)
    )
    by_platform = {row.platform: row for row in rows.scalars()}
    return [
        PlatformChip(
            platform=name,
            signed_in=bool(by_platform[name].signed_in) if name in by_platform else False,
            last_seen_at=by_platform[name].last_seen_at if name in by_platform else None,
        )
        for name in ("linkedin", "naukri")
    ]


async def build_me(db: AsyncSession, user: User) -> MeOut:
    profile = await db.get(Profile, user.id)
    preference = await db.get(Preference, user.id)
    chips = await platform_chips(db, user_id=user.id)

    onboarding = OnboardingOut(
        step=profile.onboarding_step if profile else 1,
        done=bool(profile.onboarding_done) if profile else False,
        has_resume=bool(profile and profile.resume_file_key),
        parse_status=profile.parse_status if profile else "none",
        needs_risk_consent=not bool(profile and profile.risk_accepted_at),
    )

    return MeOut(
        user=user_out(user),
        onboarding=onboarding,
        platforms=chips,
        preferences_ready=bool(preference and preference.target_roles),
        llm=provider_status(),
    )
