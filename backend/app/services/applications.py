"""Application ledger writes and reads.

The unique constraint on (user_id, platform, job_id) is what makes recording
idempotent: a retried step, a duplicated observation or a resumed tab updates the
same row instead of inflating the ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contract.models import Observation
from app.core.errors import NotFound
from app.core.timeutils import utcnow
from app.db.enums import ApplicationReason, ApplicationStatus
from app.db.models import Application
from app.db.types import JsonDict  # noqa: F401  (typing clarity for answers_used)


async def record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID | None,
    observation: Observation,
    status: str,
    reason: str | None,
    answers_used: dict | None = None,
    trace_id: str | None = None,
) -> tuple[Application, bool]:
    job = observation.job
    now = utcnow()

    async def _find() -> Application | None:
        return (
            await db.execute(
                select(Application).where(
                    Application.user_id == user_id,
                    Application.platform == observation.platform.value,
                    Application.job_id == job.id,
                )
            )
        ).scalar_one_or_none()

    existing = await _find()
    if existing is None:
        existing = Application(
            user_id=user_id,
            platform=observation.platform.value,
            job_id=job.id,
            job_title=job.title,
            company=job.company,
            location=job.location,
            job_url=job.job_url,
            status=status,
            reason=reason,
            answers_used=answers_used or {},
            run_id=run_id,
            trace_id=trace_id,
        )
        db.add(existing)
        try:
            await db.commit()
        except IntegrityError:
            # Lost a race with a concurrent retry: update instead of duplicating.
            await db.rollback()
            existing = await _find()
            if existing is None:
                raise
            previous_status = existing.status
            existing.status = status
            existing.reason = reason
            existing.updated_at = now
            await db.commit()
            await db.refresh(existing)
            return existing, previous_status != status
        await db.refresh(existing)
        return existing, True

    previous_status = existing.status
    existing.job_title = job.title or existing.job_title
    existing.company = job.company or existing.company
    existing.location = job.location or existing.location
    existing.job_url = job.job_url or existing.job_url
    existing.status = status
    existing.reason = reason
    existing.run_id = run_id or existing.run_id
    existing.trace_id = trace_id or existing.trace_id
    if answers_used:
        existing.answers_used = answers_used
    existing.updated_at = now
    await db.commit()
    await db.refresh(existing)
    return existing, previous_status != status


async def list_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    since: datetime | None = None,
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Application]:
    conditions = [Application.user_id == user_id]
    if since is not None:
        conditions.append(Application.created_at > since)
    if status:
        conditions.append(Application.status == status)
    if platform:
        conditions.append(Application.platform == platform)

    rows = await db.execute(
        select(Application)
        .where(*conditions)
        .order_by(Application.created_at.desc())
        .limit(min(max(limit, 1), 200))
        .offset(max(offset, 0))
    )
    return list(rows.scalars())


async def get(db: AsyncSession, *, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = (
        await db.execute(
            select(Application).where(
                Application.id == application_id, Application.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if application is None:
        raise NotFound("That application no longer exists.")
    return application


async def resolve(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    status: str,
    reason: str | None = None,
) -> Application:
    application = await get(db, user_id=user_id, application_id=application_id)
    application.status = status
    if reason is not None:
        application.reason = reason
    application.updated_at = utcnow()
    await db.commit()
    await db.refresh(application)
    return application


async def attach_screenshot(
    db: AsyncSession, *, user_id: uuid.UUID, application_id: uuid.UUID, key: str
) -> Application:
    application = await get(db, user_id=user_id, application_id=application_id)
    application.screenshot_key = key
    application.updated_at = utcnow()
    await db.commit()
    await db.refresh(application)
    return application


async def today_counts(db: AsyncSession, *, user_id: uuid.UUID, since: datetime) -> dict[str, int]:
    rows = await db.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user_id, Application.created_at >= since)
        .group_by(Application.status)
    )
    counts = {status: int(total) for status, total in rows.all()}
    return {
        "applied": counts.get(ApplicationStatus.APPLIED.value, 0),
        "dry_run": counts.get(ApplicationStatus.DRY_RUN.value, 0),
        "skipped": counts.get(ApplicationStatus.SKIPPED.value, 0),
        "needs_attention": counts.get(ApplicationStatus.NEEDS_ATTENTION.value, 0),
        "resolved": counts.get(ApplicationStatus.RESOLVED.value, 0),
        "failed": counts.get(ApplicationStatus.FAILED.value, 0),
    }


async def unresolved_count(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    total = await db.execute(
        select(func.count())
        .select_from(Application)
        .where(
            Application.user_id == user_id,
            Application.status == ApplicationStatus.NEEDS_ATTENTION.value,
        )
    )
    return int(total.scalar_one())


REASON_LABELS: dict[str, str] = {
    ApplicationReason.EXTERNAL_REDIRECT.value: "Applies on the company's own site",
    ApplicationReason.ALREADY_APPLIED.value: "Already applied",
    ApplicationReason.POOR_FIT.value: "Not a match for your roles",
    ApplicationReason.SENSITIVE_QUESTION.value: "Needs your own answer",
    ApplicationReason.LOW_CONFIDENCE.value: "An answer was not confident enough",
    ApplicationReason.UNKNOWN_QUESTION.value: "A question had no saved answer",
    ApplicationReason.CAPTCHA.value: "CAPTCHA on the page",
    ApplicationReason.SECURITY_CHECKPOINT.value: "Security check on the page",
    ApplicationReason.WARNING_BANNER.value: "Warning banner on the page",
    ApplicationReason.FORCED_LOGOUT.value: "You were signed out",
    ApplicationReason.RATE_LIMITED.value: "Platform rate limit",
    ApplicationReason.UNRECOGNIZED_PAGE.value: "Page not recognised",
    ApplicationReason.SUSPICIOUS_CONTENT.value: "Page contained text aimed at automated tools",
    ApplicationReason.FORM_ERROR.value: "The form could not be filled safely",
    ApplicationReason.INTERRUPTED.value: "Run was interrupted",
    ApplicationReason.CAP_REACHED.value: "Run limit reached",
    ApplicationReason.DRY_RUN_COMPLETE.value: "Practice run: filled but not submitted",
}
