"""Users and dashboard sessions.

A user is identified by their Google subject claim (``google_sub``), which is
stable across email changes. There is no password column anywhere in this schema:
authentication is Google-only, by decision D1.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import PlanTier, enum_check
from app.db.mixins import CreatedAtMixin


class User(CreatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (enum_check("plan", tuple(PlanTier), "plan_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    # Subscription tier. Limits are in app/safety/plans.py, not in the column.
    plan: Mapped[str] = mapped_column(
        String(16), default=PlanTier.REGULAR.value, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(CreatedAtMixin, Base):
    """Opaque server-side session, addressed by the httpOnly ``aa_session`` cookie."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
