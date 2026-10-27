"""Filling a form or answering a chat questionnaire.

Order per field: profile rules, then the saved answer bank, then (only if budget
allows) the model. Anything sensitive or unresolved turns the whole step into a
HITL stop, and we deliberately send no actions in that case: a half-filled form
with a human finishing it by hand is safer than a partially automated one.
"""

from __future__ import annotations

import re

from app.agents.context import StepContext
from app.agents.state import AgentState
from app.agents.tools import attach_resume, check, click, fill_text, select_option, submit
from app.contract.models import Action, ElementKind, Observation, StepStatus
from app.db.enums import ApplicationReason, ApplicationStatus
from app.services.answers import AnswerResult, answer_question, detect_sensitive

ROUTE_SUBMIT = "submit"
ROUTE_HITL = "hitl"
ROUTE_DONE = "done"

_SUBMIT_LABEL = re.compile(
    r"^\s*(submit|submit\s+application|send\s+application|confirm\s+and\s+submit|finish|apply)\s*$",
    re.IGNORECASE,
)
_NEXT_LABEL = re.compile(
    r"^\s*(next|continue|save\s*(&|and)\s*continue|review|review\s+application|proceed|save)\s*$",
    re.IGNORECASE,
)
_CONSENT_LABEL = re.compile(
    r"\b(i\s+agree|agree\s+to|consent|terms|privacy\s+policy|acknowledge|certify)\b",
    re.IGNORECASE,
)
_AFFIRMATIVE = {"yes", "y", "true", "1", "i agree", "agree", "confirmed", "ok"}

_SEVERITY = {
    ApplicationReason.SENSITIVE_QUESTION.value: 0,
    ApplicationReason.LOW_CONFIDENCE.value: 1,
    ApplicationReason.UNKNOWN_QUESTION.value: 2,
}


def _wire(actions: list[Action]) -> list[dict]:
    return [action.model_dump(mode="json") for action in actions]


def _action_for(kind: ElementKind, ref: str, value: str) -> Action | None:
    if kind is ElementKind.TEXT:
        return fill_text(ref, value)
    if kind in {ElementKind.SELECT, ElementKind.RADIO}:
        return select_option(ref, value)
    if kind is ElementKind.CHECKBOX:
        return check(ref) if value.strip().lower() in _AFFIRMATIVE else None
    if kind is ElementKind.FILE:
        return attach_resume(ref)
    return None


def _pick_worst(unresolved: list[tuple[str, AnswerResult]]) -> AnswerResult:
    return min(unresolved, key=lambda item: _SEVERITY.get(item[1].reason or "", 9))[1]


async def handle_form(state: AgentState, ctx: StepContext) -> dict:
    observation = Observation.model_validate(state["observation"])
    notes = list(state.get("notes") or [])
    answers_used: dict[str, str] = dict(state.get("answers_used") or {})
    llm_calls = int(state.get("llm_calls") or 0)

    if ctx.profile is None:
        return {
            "route": ROUTE_HITL,
            "status": StepStatus.HITL.value,
            "reason": ApplicationReason.UNKNOWN_QUESTION.value,
            "job_status": ApplicationStatus.NEEDS_ATTENTION.value,
            "job_reason": ApplicationReason.UNKNOWN_QUESTION.value,
            "actions": [],
            "llm_calls": llm_calls,
            "notes": [*notes, "no_profile"],
        }

    actions: list[Action] = []
    unresolved: list[tuple[str, AnswerResult]] = []
    answered_by_question: dict[str, AnswerResult] = {}
    remaining_budget = max(ctx.llm_calls_left - llm_calls, 0)

    pending: list[tuple[str, str, list[str], ElementKind, bool]] = []
    if observation.chat is not None:
        pending.append(
            (observation.chat.input_ref, observation.chat.question, [], ElementKind.TEXT, True)
        )

    for element in observation.elements:
        if element.kind in {ElementKind.BUTTON, ElementKind.FILE}:
            continue
        if element.value:
            continue
        if not element.label.strip():
            continue
        pending.append((element.ref, element.label, list(element.options), element.kind, element.required))

    for element in observation.elements:
        if element.kind is ElementKind.FILE and not element.value:
            actions.append(attach_resume(element.ref))

    for ref, label, options, kind, required in pending:
        if kind is ElementKind.CHECKBOX and _CONSENT_LABEL.search(label) and not detect_sensitive(label):
            # Standard application consent, already agreed to during onboarding.
            actions.append(check(ref))
            answers_used[label] = "Yes"
            continue

        cached = answered_by_question.get(label)
        if cached is not None:
            action = _action_for(kind, ref, cached.value or "") if cached.resolved else None
            if action is not None:
                actions.append(action)
            continue

        result = await answer_question(
            ctx.db,
            user_id=ctx.user_id,
            question=label,
            options=options,
            profile=ctx.profile,
            preferences=ctx.preferences,
            llm_calls_left=max(remaining_budget, 0),
            allow_llm=remaining_budget > 0,
        )
        answered_by_question[label] = result
        if result.llm_used:
            llm_calls += 1
            remaining_budget = max(remaining_budget - 1, 0)
            notes.append(f"llm_answer:{label[:60]}")

        if not result.resolved:
            optional_and_unknown = (
                not required and result.reason == ApplicationReason.UNKNOWN_QUESTION.value
            )
            if result.sensitive or not optional_and_unknown:
                unresolved.append((label, result))
            continue

        action = _action_for(kind, ref, result.value or "")
        if action is not None:
            actions.append(action)
            answers_used[label] = result.value or ""

    if unresolved:
        worst = _pick_worst(unresolved)
        reason = worst.reason or ApplicationReason.UNKNOWN_QUESTION.value
        missing = [label for label, _ in unresolved][:5]
        return {
            "route": ROUTE_HITL,
            "status": StepStatus.HITL.value,
            "reason": reason,
            "job_status": ApplicationStatus.NEEDS_ATTENTION.value,
            "job_reason": reason,
            "actions": [],
            "answers_used": answers_used,
            "llm_calls": llm_calls,
            "notes": [*notes, f"hitl:{reason}", *missing],
        }

    buttons = [element for element in observation.elements if element.kind is ElementKind.BUTTON]
    submit_button = next(
        (element for element in buttons if _SUBMIT_LABEL.match(element.label)), None
    )
    next_button = next((element for element in buttons if _NEXT_LABEL.match(element.label)), None)

    if submit_button is not None:
        return {
            "route": ROUTE_SUBMIT,
            "status": StepStatus.CONTINUE.value,
            "actions": _wire(actions),
            "answers_used": answers_used,
            "llm_calls": llm_calls,
            "notes": notes,
        }

    if next_button is not None:
        actions.append(click(next_button.ref))

    return {
        "route": ROUTE_DONE,
        "status": StepStatus.CONTINUE.value if actions else StepStatus.DONE.value,
        "actions": _wire(actions),
        "answers_used": answers_used,
        "llm_calls": llm_calls,
        "notes": notes,
    }


def prepare_submit(state: AgentState, ctx: StepContext) -> dict:
    """Last gate before the application leaves the user's hands."""
    actions = [Action.model_validate(action) for action in state.get("actions") or []]
    answers_used = dict(state.get("answers_used") or {})

    if ctx.dry_run:
        return {
            "status": StepStatus.DONE.value,
            "reason": ApplicationReason.DRY_RUN_COMPLETE.value,
            "job_status": ApplicationStatus.DRY_RUN.value,
            "job_reason": ApplicationReason.DRY_RUN_COMPLETE.value,
            "actions": _wire(actions),
        }

    actions.append(submit())
    return {
        "status": StepStatus.CONTINUE.value,
        "actions": _wire(actions),
        # Recorded now, not on the confirmation page, so an interrupted tab still
        # leaves an honest entry in the ledger.
        "job_status": ApplicationStatus.APPLIED.value,
        "job_reason": None,
        "answers_used": answers_used,
    }
