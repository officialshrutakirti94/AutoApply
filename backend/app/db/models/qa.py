"""Saved screening answers."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import QaSource, enum_check
from app.db.mixins import TimestampMixin


class QaBankEntry(TimestampMixin, Base):
    __tablename__ = "qa_bank"
    __table_args__ = (
        UniqueConstraint("user_id", "question_pattern", name="uq_qa_bank_user_id_question_pattern"),
        enum_check("source", tuple(QaSource), "source_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Normalised (lowercased, punctuation-free) so the same question matches again.
    question_pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default=QaSource.USER, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
