"""One row per job the agent touched.

``UNIQUE (user_id, platform, job_id)`` is the duplicate-application guard: the same
job can never be logged twice, which also makes the agent step endpoint idempotent
under retries.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import ApplicationReason, ApplicationStatus, Platform, enum_check
from app.db.mixins import TimestampMixin
from app.db.types import JsonDict


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "job_id", name="uq_applications_user_platform_job"),
        Index("ix_applications_user_id_created_at", "user_id", "created_at"),
        enum_check("platform", tuple(Platform), "platform_valid"),
        enum_check("status", tuple(ApplicationStatus), "status_valid"),
        enum_check("reason", tuple(ApplicationReason), "reason_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    job_id: Mapped[str] = mapped_column(String(120), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    job_url: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(40))
    screenshot_key: Mapped[str | None] = mapped_column(String(500))
    answers_used: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict, nullable=False)

    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    trace_id: Mapped[str | None] = mapped_column(String(64))
