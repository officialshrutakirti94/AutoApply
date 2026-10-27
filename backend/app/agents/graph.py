"""The shared agent graph.

Deliberately not a checkpointer graph: the extension calls this as an HTTP step
function with the current page in hand, so the resumable state is the run row in
Postgres, not an in-memory saver. That survives a reloaded tab, a restarted worker
and a different instance, which is exactly the reliability problem the plan calls
out for MV3.

Shape:

    START -> intake -> (hard_stop | skip | hitl | assess_fit | handle_form | confirm)
    assess_fit -> (open_apply | skip)
    open_apply -> END
    handle_form -> (prepare_submit | hitl | END)
    prepare_submit -> END
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langgraph.graph import END, START, StateGraph

from app.agents.context import StepContext
from app.agents.nodes import (
    ROUTE_DONE,
    ROUTE_HITL,
    ROUTE_OPEN,
    ROUTE_SUBMIT,
    assess_fit,
    confirm,
    handle_form,
    hard_stop,
    hitl,
    intake,
    open_apply,
    prepare_submit,
    skip_reason,
)
from app.agents.state import (
    ROUTE_CONFIRM,
    ROUTE_FIT,
    ROUTE_FORM,
    ROUTE_HARD_STOP,
    ROUTE_SKIP,
    AgentState,
)
from app.agents.tools import build_response
from app.agents.tracing import traceable
from app.contract.models import Action, AgentResponse, Observation, StepStatus
from app.core.logging import get_logger
from app.core.security import new_trace_id
from app.db.enums import ApplicationReason, ApplicationStatus

log = get_logger("agent_graph")


@dataclass(slots=True)
class StepOutcome:
    response: AgentResponse
    job_status: str | None = None
    job_reason: str | None = None
    answers_used: dict[str, str] = field(default_factory=dict)
    llm_calls: int = 0
    route: str = ""
    trace_id: str = ""


def _route_of(state: AgentState) -> str:
    return str(state.get("route") or ROUTE_SKIP)


def build_graph(ctx: StepContext):
    graph = StateGraph(AgentState)

    graph.add_node("intake", intake)
    graph.add_node("hard_stop", hard_stop)
    graph.add_node("skip_reason", skip_reason)
    graph.add_node("hitl", hitl)
    graph.add_node("assess_fit", lambda state: assess_fit(state, ctx))
    graph.add_node("open_apply", lambda state: open_apply(state, ctx))
    # handle_form is async (it may call the answer engine), so it needs an async
    # wrapper: a sync lambda would return an un-awaited coroutine.
    async def _handle_form(state: AgentState) -> dict:
        return await handle_form(state, ctx)

    graph.add_node("handle_form", _handle_form)
    graph.add_node("prepare_submit", lambda state: prepare_submit(state, ctx))
    graph.add_node("confirm", lambda state: confirm(state, ctx))

    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake",
        _route_of,
        {
            ROUTE_HARD_STOP: "hard_stop",
            ROUTE_SKIP: "skip_reason",
            ROUTE_HITL: "hitl",
            ROUTE_FIT: "assess_fit",
            ROUTE_FORM: "handle_form",
            ROUTE_CONFIRM: "confirm",
        },
    )
    graph.add_conditional_edges(
        "assess_fit",
        _route_of,
        {ROUTE_OPEN: "open_apply", ROUTE_SKIP: "skip_reason"},
    )
    graph.add_conditional_edges(
        "handle_form",
        _route_of,
        {ROUTE_SUBMIT: "prepare_submit", ROUTE_HITL: END, ROUTE_DONE: END},
    )

    for terminal in ("hard_stop", "skip_reason", "hitl", "open_apply", "prepare_submit", "confirm"):
        graph.add_edge(terminal, END)

    return graph.compile()


@traceable("autoapply_agent_step")
async def _invoke(compiled, state: AgentState) -> AgentState:
    return await compiled.ainvoke(state)  # type: ignore[return-value]


def _fallback(reason: str, trace_id: str, route: str) -> StepOutcome:
    return StepOutcome(
        response=AgentResponse(actions=[], status=StepStatus.HITL, reason=reason),
        job_status=ApplicationStatus.NEEDS_ATTENTION.value,
        job_reason=reason,
        route=route,
        trace_id=trace_id,
    )


async def run_agent_step(ctx: StepContext, observation: Observation) -> StepOutcome:
    """One observation in, one decision out. Never raises for page conditions."""
    trace_id = new_trace_id()
    initial: AgentState = {
        "observation": observation.model_dump(mode="json"),
        "actions": [],
        "answers_used": {},
        "notes": [],
        "llm_calls": 0,
    }

    try:
        final = await _invoke(build_graph(ctx), initial)
    except Exception:
        log.exception("agent_step_failed", run_id=str(ctx.run.id), platform=observation.platform.value)
        return _fallback(ApplicationReason.FORM_ERROR.value, trace_id, "error")

    try:
        actions = [Action.model_validate(item) for item in final.get("actions") or []]
        status = StepStatus(str(final.get("status") or StepStatus.DONE.value))
        response = build_response(
            observation=observation,
            actions=actions,
            status=status,
            reason=final.get("reason"),
            dry_run=ctx.dry_run,
        )
    except Exception:
        log.exception("agent_response_invalid", run_id=str(ctx.run.id))
        return _fallback(ApplicationReason.FORM_ERROR.value, trace_id, "invalid_response")

    job_status = final.get("job_status")
    if job_status is None and response.status is StepStatus.CONTINUE:
        job_status = None

    return StepOutcome(
        response=response,
        job_status=job_status,
        job_reason=final.get("job_reason"),
        answers_used=dict(final.get("answers_used") or {}),
        llm_calls=int(final.get("llm_calls") or 0),
        route=str(final.get("route") or ""),
        trace_id=trace_id,
    )
