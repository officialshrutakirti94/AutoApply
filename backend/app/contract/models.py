"""Pydantic mirror of ``packages/shared/contract.schema.json``.

The JSON Schema is the source of truth shared with the TypeScript extension;
``tests/test_contract.py`` asserts the two stay in sync. These models are stricter
in one useful way: they cross-validate that each action type carries the fields it
needs, so a malformed decision fails here rather than on a live job page.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

REF_PATTERN = r"^[a-z][0-9]{1,4}$"
MAX_ACTIONS_PER_STEP = 10


class Platform(StrEnum):
    LINKEDIN = "linkedin"
    NAUKRI = "naukri"


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


# Signals that mean "get out now" rather than "carry on carefully".
HARD_STOP_SIGNALS = frozenset(
    {
        Signal.CAPTCHA,
        Signal.CHECKPOINT,
        Signal.WARNING_BANNER,
        Signal.FORCED_LOGOUT,
        Signal.RATE_LIMITED,
    }
)


class JobSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    job_url: str | None = Field(default=None, max_length=2000)
    already_applied: bool = False
    external: bool = False


class FormElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(pattern=REF_PATTERN)
    kind: ElementKind
    label: str = Field(default="", max_length=400)
    options: list[str] = Field(default_factory=list, max_length=100)
    required: bool = False
    value: str | None = Field(default=None, max_length=2000)


class ChatPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=2000)
    input_ref: str = Field(pattern=REF_PATTERN)


class Observation(BaseModel):
    """What the page looks like right now, described in platform-neutral terms."""

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    platform: Platform
    page_type: PageType
    job: JobSummary
    elements: list[FormElement] = Field(default_factory=list, max_length=200)
    chat: ChatPrompt | None = None
    page_text_digest: str | None = Field(default=None, max_length=4000)
    signals: list[Signal] = Field(default_factory=list, max_length=10)

    @property
    def refs(self) -> set[str]:
        refs = {element.ref for element in self.elements}
        if self.chat is not None:
            refs.add(self.chat.input_ref)
        return refs

    @property
    def hard_stop_signals(self) -> list[Signal]:
        return [signal for signal in self.signals if signal in HARD_STOP_SIGNALS]

    def has_signal(self, *candidates: Signal) -> bool:
        return any(signal in self.signals for signal in candidates)


class Action(BaseModel):
    """One allow-listed thing the extension may do. ``ref`` only, never a selector."""

    model_config = ConfigDict(extra="forbid")

    type: ActionType
    ref: str | None = Field(default=None, pattern=REF_PATTERN)
    value: str | None = Field(default=None, max_length=2000)
    ms: int | None = Field(default=None, ge=100, le=30000)

    @model_validator(mode="after")
    def _check_required_fields(self) -> Action:
        needs_ref_value = {ActionType.FILL_TEXT, ActionType.SELECT_OPTION}
        needs_ref = {ActionType.CHECK, ActionType.CLICK, ActionType.ATTACH_RESUME}

        if self.type in needs_ref_value:
            if not self.ref or self.value is None:
                raise ValueError(f"{self.type} requires both ref and value")
        elif self.type in needs_ref:
            if not self.ref:
                raise ValueError(f"{self.type} requires ref")
        elif self.type is ActionType.WAIT:
            if self.ms is None:
                raise ValueError("wait requires ms")
        else:  # submit, finish
            if self.ref is not None:
                raise ValueError(f"{self.type} must not target a ref")
        return self


class AgentResponse(BaseModel):
    """The decision: what to do next, and why we stopped if we did."""

    model_config = ConfigDict(extra="forbid")

    actions: list[Action] = Field(default_factory=list, max_length=MAX_ACTIONS_PER_STEP)
    status: StepStatus
    reason: str | None = Field(default=None, max_length=60)
    # Counters for the extension popup. Never a source of actions.
    meta: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _reason_when_not_continuing(self) -> AgentResponse:
        if self.status in {StepStatus.HITL, StepStatus.STOP} and not self.reason:
            raise ValueError(f"status '{self.status}' requires a reason")
        if self.status is StepStatus.CONTINUE and not self.actions:
            raise ValueError("status 'continue' requires at least one action")
        return self
