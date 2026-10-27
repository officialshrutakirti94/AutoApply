"""Allow-listed action builders.

The only way the backend can tell the extension to do something is through these
constructors, and :func:`validate_actions` refuses anything referencing a ref that
was not in the current observation. That is the code-level half of the "handles
only, no selectors, no URLs" rule from the plan.
"""

from __future__ import annotations

from app.contract.models import (
    MAX_ACTIONS_PER_STEP,
    Action,
    ActionType,
    AgentResponse,
    Observation,
    StepStatus,
)


class ActionRejected(ValueError):
    """An action would have escaped the allow-list."""


def fill_text(ref: str, value: str) -> Action:
    return Action(type=ActionType.FILL_TEXT, ref=ref, value=value)


def select_option(ref: str, value: str) -> Action:
    return Action(type=ActionType.SELECT_OPTION, ref=ref, value=value)


def check(ref: str) -> Action:
    return Action(type=ActionType.CHECK, ref=ref)


def attach_resume(ref: str) -> Action:
    return Action(type=ActionType.ATTACH_RESUME, ref=ref)


def click(ref: str) -> Action:
    return Action(type=ActionType.CLICK, ref=ref)


def wait(ms: int) -> Action:
    return Action(type=ActionType.WAIT, ms=ms)


def submit() -> Action:
    return Action(type=ActionType.SUBMIT)


def finish() -> Action:
    return Action(type=ActionType.FINISH)


def validate_actions(actions: list[Action], observation: Observation) -> list[Action]:
    """Drop anything that references an element we were not shown."""
    allowed = observation.refs
    validated: list[Action] = []
    for action in actions:
        if action.ref is not None and action.ref not in allowed:
            raise ActionRejected(f"Action {action.type} references unknown ref {action.ref!r}")
        validated.append(action)

    if len(validated) > MAX_ACTIONS_PER_STEP:
        raise ActionRejected(f"Too many actions in one step ({len(validated)})")
    return validated


def build_response(
    *,
    observation: Observation,
    actions: list[Action],
    status: StepStatus,
    reason: str | None = None,
    dry_run: bool = False,
) -> AgentResponse:
    """Assemble and validate the outgoing decision, with dry-run as a hard gate."""
    cleaned = validate_actions(list(actions), observation)

    if dry_run:
        # Belt and braces: the submit node already refuses, this makes it impossible.
        if any(action.type is ActionType.SUBMIT for action in cleaned):
            cleaned = [action for action in cleaned if action.type is not ActionType.SUBMIT]
            status = StepStatus.DONE
            reason = reason or "dry_run_complete"

    if status is StepStatus.CONTINUE and not cleaned:
        raise ActionRejected("continue with no actions")

    return AgentResponse(actions=cleaned, status=status, reason=reason)
