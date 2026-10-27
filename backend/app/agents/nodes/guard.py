"""Entry guard and the terminal "we stopped" nodes.

The first node decides everything safety-related before any judgement about the
job is made. A hard stop wins over every other consideration: if the page shows a
CAPTCHA, we do not care how good the job is.
"""

from __future__ import annotations

from app.agents.state import (
    ROUTE_CONFIRM,
    ROUTE_FIT,
    ROUTE_FORM,
    ROUTE_HARD_STOP,
    ROUTE_HITL,
    ROUTE_SKIP,
    AgentState,
)
from app.contract.models import HARD_STOP_SIGNALS, Observation, PageType, Signal
from app.db.enums import ApplicationReason, ApplicationStatus, StepStatus
from app.services.answers import detect_injection

_SIGNAL_TO_REASON: dict[Signal, str] = {
    Signal.CAPTCHA: ApplicationReason.CAPTCHA.value,
    Signal.CHECKPOINT: ApplicationReason.SECURITY_CHECKPOINT.value,
    Signal.WARNING_BANNER: ApplicationReason.WARNING_BANNER.value,
    Signal.FORCED_LOGOUT: ApplicationReason.FORCED_LOGOUT.value,
    Signal.RATE_LIMITED: ApplicationReason.RATE_LIMITED.value,
}

_REASON_MESSAGES: dict[str, str] = {
    ApplicationReason.CAPTCHA.value: "The platform showed a CAPTCHA. Autopilot stopped.",
    ApplicationReason.SECURITY_CHECKPOINT.value: "The platform showed a security check. Autopilot stopped.",
    ApplicationReason.WARNING_BANNER.value: "The platform showed a warning. Autopilot stopped.",
    ApplicationReason.FORCED_LOGOUT.value: "You were signed out. Autopilot stopped.",
    ApplicationReason.RATE_LIMITED.value: "The platform is rate-limiting requests. Autopilot stopped.",
    ApplicationReason.EXTERNAL_REDIRECT.value: "This job applies on the company's own site.",
    ApplicationReason.ALREADY_APPLIED.value: "You already applied to this job.",
    ApplicationReason.SUSPICIOUS_CONTENT.value: "This job page contained text aimed at automated tools.",
    ApplicationReason.UNRECOGNIZED_PAGE.value: "This page was not recognised.",
    ApplicationReason.POOR_FIT.value: "This job does not match your roles or is on your block list.",
    ApplicationReason.SENSITIVE_QUESTION.value: "A question needs your own answer.",
    ApplicationReason.UNKNOWN_QUESTION.value: "A question had no saved answer.",
    ApplicationReason.LOW_CONFIDENCE.value: "An answer was not confident enough to submit.",
    ApplicationReason.FORM_ERROR.value: "The form could not be filled safely.",
}


def message_for(reason: str | None) -> str:
    return _REASON_MESSAGES.get(reason or "", "Autopilot needs you for this one.")


def intake(state: AgentState) -> dict:
    observation = Observation.model_validate(state["observation"])
    job = observation.job

    hard = observation.hard_stop_signals
    if hard:
        reason = _SIGNAL_TO_REASON.get(hard[0], ApplicationReason.SECURITY_CHECKPOINT.value)
        return {"route": ROUTE_HARD_STOP, "reason": reason}

    if observation.page_type is PageType.UNKNOWN or observation.has_signal(Signal.UNKNOWN_PAGE):
        return {"route": ROUTE_HITL, "reason": ApplicationReason.UNRECOGNIZED_PAGE.value}

    if observation.page_type is PageType.EXTERNAL or job.external:
        return {"route": ROUTE_SKIP, "reason": ApplicationReason.EXTERNAL_REDIRECT.value}

    if job.already_applied:
        return {"route": ROUTE_SKIP, "reason": ApplicationReason.ALREADY_APPLIED.value}

    injection = detect_injection(observation.page_text_digest)
    if injection or observation.has_signal(Signal.SUSPICIOUS_CONTENT):
        return {"route": ROUTE_SKIP, "reason": ApplicationReason.SUSPICIOUS_CONTENT.value}

    if observation.page_type in {PageType.SEARCH_RESULTS, PageType.JOB_DETAIL}:
        return {"route": ROUTE_FIT}
    if observation.page_type in {PageType.APPLY_FORM, PageType.CHAT_QUESTION}:
        return {"route": ROUTE_FORM}
    if observation.page_type is PageType.CONFIRMATION:
        return {"route": ROUTE_CONFIRM}

    return {"route": ROUTE_HITL, "reason": ApplicationReason.UNRECOGNIZED_PAGE.value}


def hard_stop(state: AgentState) -> dict:
    reason = state.get("reason") or ApplicationReason.SECURITY_CHECKPOINT.value
    return {
        "status": StepStatus.STOP.value,
        "reason": reason,
        "job_status": ApplicationStatus.NEEDS_ATTENTION.value,
        "job_reason": reason,
        "actions": [],
        "notes": [*state.get("notes", []), f"hard_stop:{reason}"],
    }


def skip_reason(state: AgentState) -> dict:
    reason = state.get("reason") or ApplicationReason.POOR_FIT.value
    return {
        "status": StepStatus.DONE.value,
        "reason": reason,
        "job_status": ApplicationStatus.SKIPPED.value,
        "job_reason": reason,
        "actions": [],
    }


def hitl(state: AgentState) -> dict:
    reason = state.get("reason") or ApplicationReason.UNKNOWN_QUESTION.value
    return {
        "status": StepStatus.HITL.value,
        "reason": reason,
        "job_status": ApplicationStatus.NEEDS_ATTENTION.value,
        "job_reason": reason,
        "actions": [],
    }


__all__ = [
    "HARD_STOP_SIGNALS",
    "hard_stop",
    "hitl",
    "intake",
    "message_for",
    "skip_reason",
]
