"""Platform sign-in state, extension tokens and pairing codes."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import Platform, enum_check
from app.db.mixins import CreatedAtMixin


class PlatformConnection(CreatedAtMixin, Base):
    """Last-known signed-in state per platform, reported by the extension."""

    __tablename__ = "platform_connections"
    __table_args__ = (enum_check("platform", tuple(Platform), "platform_valid"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(20), primary_key=True)
    signed_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExtensionToken(CreatedAtMixin, Base):
    """Scoped bearer token for one browser install. Only the hash is stored."""

    __tablename__ = "extension_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="extension", nullable=False)
    install_id: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(120))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtensionPairingCode(CreatedAtMixin, Base):
    """Single-use, short-lived code that trades for an extension token."""

    __tablename__ = "extension_pairing_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
