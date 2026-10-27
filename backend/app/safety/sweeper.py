"""Background maintenance.

Three jobs, two cadences:

* every minute  - mark runs whose heartbeat stopped as ``interrupted``
* every hour    - expire sessions, drop used pairing codes, delete expired screenshots

Runs as one asyncio task inside the API process. That is correct for the v1
single-instance deployment; a multi-instance deployment must move this to a cron
job hitting ``POST /internal/sweep`` instead, which is also implemented.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.timeutils import utcnow
from app.db.enums import RunStatus
from app.db.models import AgentRun, Application, ExtensionPairingCode, UserSession
from app.db.session import get_session_factory

log = get_logger("sweeper")

SCREENSHOT_BATCH = 200


@dataclass(slots=True)
class SweepReport:
    interrupted_runs: int = 0
    expired_sessions: int = 0
    expired_pairing_codes: int = 0
    deleted_screenshots: int = 0

    def as_dict(self) -> dict:
        return {
            "interrupted_runs": self.interrupted_runs,
            "expired_sessions": self.expired_sessions,
            "expired_pairing_codes": self.expired_pairing_codes,
            "deleted_screenshots": self.deleted_screenshots,
        }


async def interrupt_stale_runs(db: AsyncSession) -> int:
    now = utcnow()
    cutoff = now - timedelta(seconds=settings.safety_heartbeat_timeout_seconds)

    stale = list(
        (
            await db.execute(
                select(AgentRun).where(
                    AgentRun.status == RunStatus.RUNNING.value,
                    AgentRun.last_heartbeat_at < cutoff,
                )
            )
        ).scalars()
    )

    for run in stale:
        run.status = RunStatus.INTERRUPTED.value
        run.ended_at = now
        run.stop_reason = "heartbeat_timeout"

    if stale:
        await db.commit()
        log.info("runs_interrupted", count=len(stale))
    return len(stale)


async def _expire_sessions(db: AsyncSession) -> int:
    now = utcnow()
    cutoff = now - timedelta(days=1)
    rows = list(
        (
            await db.execute(
                select(UserSession).where(
                    or_(UserSession.expires_at < cutoff, UserSession.revoked_at < cutoff)
                )
            )
        ).scalars()
    )
    for row in rows:
        await db.delete(row)
    if rows:
        await db.commit()
    return len(rows)


async def _expire_pairing_codes(db: AsyncSession) -> int:
    cutoff = utcnow() - timedelta(hours=1)
    rows = list(
        (
            await db.execute(
                select(ExtensionPairingCode).where(ExtensionPairingCode.expires_at < cutoff)
            )
        ).scalars()
    )
    for row in rows:
        await db.delete(row)
    if rows:
        await db.commit()
    return len(rows)


async def _purge_screenshots(db: AsyncSession) -> int:
    """Screenshots are evidence for stuck steps, not an archive. Delete after 14 days."""
    cutoff = utcnow() - timedelta(days=settings.screenshot_retention_days)
    rows = list(
        (
            await db.execute(
                select(Application)
                .where(Application.screenshot_key.is_not(None), Application.created_at < cutoff)
                .limit(SCREENSHOT_BATCH)
            )
        ).scalars()
    )
    if not rows:
        return 0

    from app.services.storage import get_storage

    storage = get_storage()
    deleted = 0
    for row in rows:
        key = row.screenshot_key
        if key:
            try:
                await storage.delete(key)
            except Exception:  # object may already be gone
                log.warning("screenshot_delete_failed", key=key)
        row.screenshot_key = None
        deleted += 1

    await db.commit()
    return deleted


async def sweep_once(db: AsyncSession, *, full: bool = True) -> SweepReport:
    report = SweepReport(interrupted_runs=await interrupt_stale_runs(db))
    if full:
        report.expired_sessions = await _expire_sessions(db)
        report.expired_pairing_codes = await _expire_pairing_codes(db)
        report.deleted_screenshots = await _purge_screenshots(db)
    return report


async def maintenance_loop(
    *,
    interval_seconds: int = 60,
    full_sweep_every_minutes: int | None = None,
) -> None:
    every_minutes = full_sweep_every_minutes or settings.session_sweep_interval_minutes
    ticks_per_full_sweep = max(int(every_minutes * 60 / max(interval_seconds, 1)), 1)
    tick = 0

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            tick += 1
            full = tick % ticks_per_full_sweep == 0
            async with get_session_factory()() as db:
                report = await sweep_once(db, full=full)
            if full:
                log.info("sweep_complete", **report.as_dict())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sweep_failed")
