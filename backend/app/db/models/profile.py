"""Profile, preferences and their shared vocabularies."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import enum_check
from app.db.mixins import TimestampMixin
from app.db.types import JsonDict, StringList

PARSE_STATUSES = ("none", "pending", "parsed", "failed", "manual")
WORK_MODES = ("remote", "hybrid", "onsite")
EXPERIENCE_LEVELS = ("entry", "mid", "experienced")


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"
    __table_args__ = (enum_check("parse_status", PARSE_STATUSES, "parse_status_valid"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    full_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(200))

    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    naukri_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))
    other_links: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)

    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)
    years_of_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    current_title: Mapped[str | None] = mapped_column(String(200))
    current_company: Mapped[str | None] = mapped_column(String(200))
    education: Mapped[list[dict[str, Any]]] = mapped_column(JsonDict, default=list, nullable=False)

    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    current_ctc_lpa: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    expected_ctc_lpa: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    work_authorization: Mapped[str | None] = mapped_column(String(200))

    resume_file_key: Mapped[str | None] = mapped_column(String(500))
    resume_parsed: Mapped[dict[str, Any] | None] = mapped_column(JsonDict)
    parse_status: Mapped[str] = mapped_column(String(16), default="none", nullable=False)

    onboarding_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Preference(TimestampMixin, Base):
    __tablename__ = "preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    target_roles: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)
    domains: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)
    locations: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)
    work_mode: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)
    experience_level: Mapped[str | None] = mapped_column(String(20))
    platforms: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)

    # {"start": "09:00", "end": "21:00", "timezone": "Asia/Kolkata"}
    active_hours: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict, nullable=False)
    daily_cap: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    blacklist_companies: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)
    blacklist_keywords: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)
