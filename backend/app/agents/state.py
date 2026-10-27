"""Graph state.

LangGraph merges each node's returned dict into this state. There is no
checkpointer: the loop is an HTTP step function, so the resumable state lives in
``agent_runs.agent_state`` on the server instead. That is what lets a reloaded tab
continue rather than restart an application.
"""

from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    # input
    observation: dict

    # routing
    route: str
    reason: str | None

    # output
    actions: list[dict]
    status: str
    job_status: str | None
    job_reason: str | None

    # bookkeeping
    answers_used: dict[str, str]
    llm_calls: int
    notes: list[str]


ROUTE_HARD_STOP = "hard_stop"
ROUTE_SKIP = "skip"
ROUTE_HITL = "hitl"
ROUTE_FIT = "fit"
ROUTE_FORM = "form"
ROUTE_CONFIRM = "confirm"
