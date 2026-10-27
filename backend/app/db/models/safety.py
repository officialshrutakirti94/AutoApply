"""Safety events: hard stops, cooldowns and blocked start attempts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import CreatedAtMixin
from app.db.types import JsonDict


class SafetyEvent(CreatedAtMixin, Base):
    __tablename__ = "safety_events"
    __table_args__ = (Index("ix_safety_events_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )

    type: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
