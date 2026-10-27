"""Terminal node for a confirmed application."""

from __future__ import annotations

from app.agents.context import StepContext
from app.agents.state import AgentState
from app.contract.models import StepStatus
from app.db.enums import ApplicationReason, ApplicationStatus


def confirm(state: AgentState, ctx: StepContext) -> dict:
    if ctx.dry_run:
        return {
            "status": StepStatus.DONE.value,
            "reason": ApplicationReason.DRY_RUN_COMPLETE.value,
            "job_status": ApplicationStatus.DRY_RUN.value,
            "job_reason": ApplicationReason.DRY_RUN_COMPLETE.value,
            "actions": [],
        }

    return {
        "status": StepStatus.DONE.value,
        "job_status": ApplicationStatus.APPLIED.value,
        "job_reason": None,
        "actions": [],
    }
