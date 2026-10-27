"""Domain vocabularies.

Stored as ``String`` with a CHECK constraint rather than a Postgres ENUM: adding a
value then costs one migration line instead of an ``ALTER TYPE`` dance.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from sqlalchemy import CheckConstraint


class Platform(StrEnum):
    LINKEDIN = "linkedin"
    NAUKRI = "naukri"


class PlanTier(StrEnum):
    """Subscription tiers. The limits live in ``app/safety/plans.py``."""

    REGULAR = "regular"
    PRO = "pro"
    PRO_PLUS = "pro_plus"


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    DRY_RUN = "dry_run"
    SKIPPED = "skipped"
    NEEDS_ATTENTION = "needs_attention"
    RESOLVED = "resolved"
    FAILED = "failed"


class ApplicationReason(StrEnum):
    EXTERNAL_REDIRECT = "external_redirect"
    ALREADY_APPLIED = "already_applied"
    POOR_FIT = "poor_fit"
    SENSITIVE_QUESTION = "sensitive_question"
    LOW_CONFIDENCE = "low_confidence"
    UNKNOWN_QUESTION = "unknown_question"
    CAPTCHA = "captcha"
    SECURITY_CHECKPOINT = "security_checkpoint"
    WARNING_BANNER = "warning_banner"
    FORCED_LOGOUT = "forced_logout"
    RATE_LIMITED = "rate_limited"
    UNRECOGNIZED_PAGE = "unrecognized_page"
    SUSPICIOUS_CONTENT = "suspicious_content"
    FORM_ERROR = "form_error"
    INTERRUPTED = "interrupted"
    CAP_REACHED = "cap_reached"
    DRY_RUN_COMPLETE = "dry_run_complete"


class RunStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"


class PageType(StrEnum):
    SEARCH_RESULTS = "search_results"
    JOB_DETAIL = "job_detail"
    APPLY_FORM = "apply_form"
    CHAT_QUESTION = "chat_question"
    CONFIRMATION = "confirmation"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class ElementKind(StrEnum):
    TEXT = "text"
    SELECT = "select"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    FILE = "file"
    BUTTON = "button"


class Signal(StrEnum):
    CAPTCHA = "captcha"
    CHECKPOINT = "checkpoint"
    WARNING_BANNER = "warning_banner"
    FORCED_LOGOUT = "forced_logout"
    RATE_LIMITED = "rate_limited"
    UNKNOWN_PAGE = "unknown_page"
    SUSPICIOUS_CONTENT = "suspicious_content"


class ActionType(StrEnum):
    FILL_TEXT = "fill_text"
    SELECT_OPTION = "select_option"
    CHECK = "check"
    ATTACH_RESUME = "attach_resume"
    CLICK = "click"
    WAIT = "wait"
    SUBMIT = "submit"
    FINISH = "finish"


class StepStatus(StrEnum):
    CONTINUE = "continue"
    DONE = "done"
    HITL = "hitl"
    STOP = "stop"


class QaSource(StrEnum):
    USER = "user"
    AI = "ai"


def enum_check(column: str, values: Iterable[str], name: str) -> CheckConstraint:
    rendered = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({rendered})", name=name)
