"""Fit check and navigation.

Two rules from the plan live here: skip jobs that do not fit, and skip anything
that would leave the platform. The extension refuses to click an off-platform link,
and this node never asks it to.
"""

from __future__ import annotations

import re

from app.agents.context import StepContext
from app.agents.state import AgentState
from app.contract.models import ElementKind, Observation, PageType
from app.db.enums import ApplicationReason, ApplicationStatus, StepStatus
from app.agents.tools import click

ROUTE_OPEN = "open"

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
_SHORT_ROLE_TOKENS = {"ai", "ml", "qa", "ux", "ui", "bi"}
_STOPWORDS = {
    "senior", "junior", "sr", "jr", "lead", "staff", "principal", "ii", "iii", "iv",
    "the", "and", "for", "with", "a", "an", "of", "at", "in", "to", "remote", "hybrid",
    "onsite", "full", "time", "part",
}

APPLY_LABEL = re.compile(
    r"(easy\s*apply|apply\s*(now|on\s*naukri|for\s*this\s*job|here)?|start\s*(your\s*)?application|\bapply\b)",
    re.IGNORECASE,
)
CARD_SKIP_LABEL = re.compile(
    r"\b(applied|next|previous|back|save|share|dismiss|report|hide|follow|already)\b",
    re.IGNORECASE,
)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall((text or "").lower())
        if (len(token) > 2 or token in _SHORT_ROLE_TOKENS) and token not in _STOPWORDS
    }


def _matches_target_roles(title: str, roles: list[str]) -> bool:
    if not roles:
        return True
    title_tokens = _tokens(title)
    if not title_tokens:
        return True
    return any(_tokens(role) & title_tokens for role in roles)


def _blocked(title: str, company: str | None, ctx: StepContext) -> bool:
    lowered_title = (title or "").lower()
    lowered_company = (company or "").lower()
    if any(word.lower() and word.lower() in lowered_title for word in ctx.blacklist_keywords):
        return True
    return any(
        name.lower() and name.lower() in lowered_company for name in ctx.blacklist_companies
    )


def assess_fit(state: AgentState, ctx: StepContext) -> dict:
    observation = Observation.model_validate(state["observation"])
    job = observation.job
    title = job.title or ""

    if _blocked(title, job.company, ctx):
        return {"route": "skip", "reason": ApplicationReason.POOR_FIT.value}

    if not _matches_target_roles(title, ctx.target_roles):
        return {"route": "skip", "reason": ApplicationReason.POOR_FIT.value}

    return {"route": ROUTE_OPEN}


def open_apply(state: AgentState, ctx: StepContext) -> dict:
    observation = Observation.model_validate(state["observation"])
    buttons = [element for element in observation.elements if element.kind is ElementKind.BUTTON]

    if observation.page_type is PageType.SEARCH_RESULTS:
        available = [
            element
            for element in buttons
            if not CARD_SKIP_LABEL.search(element.label)
        ]
        candidates = [
            element for element in available if _matches_target_roles(element.label, ctx.target_roles)
        ]
        if not candidates:
            # Search-card labels are abbreviated and often omit the role's
            # meaningful short tokens. Open one card and assess its full detail
            # title instead of repeatedly ending the run on the search page.
            candidates = available
        if not candidates:
            return {
                "status": StepStatus.DONE.value,
                "reason": "no_matching_jobs",
                "actions": [],
                "notes": [*state.get("notes", []), "no_candidates_on_page"],
            }
        return {
            "actions": [click(candidates[0].ref).model_dump(mode="json")],
            "status": StepStatus.CONTINUE.value,
        }

    apply_button = next(
        (
            element
            for element in buttons
            if APPLY_LABEL.search(element.label) and not CARD_SKIP_LABEL.search(element.label)
        ),
        None,
    )
    if apply_button is None:
        # A job detail page with no in-platform apply control means the real
        # application happens elsewhere. That is a skip, not a failure.
        return {
            "status": StepStatus.DONE.value,
            "reason": ApplicationReason.EXTERNAL_REDIRECT.value,
            "job_status": ApplicationStatus.SKIPPED.value,
            "job_reason": ApplicationReason.EXTERNAL_REDIRECT.value,
            "actions": [],
        }

    return {
        "actions": [click(apply_button.ref).model_dump(mode="json")],
        "status": StepStatus.CONTINUE.value,
    }
