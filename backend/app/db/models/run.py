"""Agent runs.

The partial unique index is the enforcement point for "one active run per user":
the database rejects a second ``running`` row even if two requests race past the
application-level check.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import Platform, RunStatus, enum_check
from app.db.mixins import TimestampMixin
from app.db.types import JsonDict


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index(
            "uq_agent_runs_one_running_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        Index("ix_agent_runs_user_id_started_at", "user_id", "started_at"),
        enum_check("platform", tuple(Platform), "platform_valid"),
        enum_check("status", tuple(RunStatus), "status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.RUNNING, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_applications: Mapped[int] = mapped_column(Integer, default=15, nullable=False)

    applied_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stuck_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(60))

    # Resume point for the extension loop: current job, filled refs, answered
    # questions. Kept server-side so a reloaded tab can continue instead of
    # restarting the same application.
    agent_state: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict, nullable=False)
