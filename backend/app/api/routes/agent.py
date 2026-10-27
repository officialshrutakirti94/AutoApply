"""The single agent endpoint: one observation in, one decision out.

This is the only route that runs the graph. It is idempotent at the ledger level
(the application upsert is keyed on job id), so the extension may retry a step
after a dropped connection.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas import AgentStepMeta
from app.contract.models import AgentResponse, Observation
from app.core.config import settings
from app.core.deps import DbSession, ExtensionAuth
from app.core.errors import Conflict
from app.core.ratelimit import check_rate_limit
from app.safety import governor
from app.services import runs as runs_service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/step", response_model=AgentResponse, response_model_exclude_none=True)
async def agent_step(
    observation: Observation,
    principal: ExtensionAuth,
    db: DbSession,
    request: Request,
) -> AgentResponse:
    await check_rate_limit(request, bucket="agent-step", window_seconds=60, limit=180)

    # Scoped lookup: another user's run id is a 404, not a leak.
    run = await runs_service.get_run(db, user_id=principal.user_id, run_id=observation.run_id)

    if await runs_service.interrupt_if_stale(db, run=run):
        raise Conflict("This run stopped responding and was marked interrupted. Start a new run.")

    outcome = await runs_service.process_step(db, run=run, observation=observation)
    await db.refresh(run)

    meta = AgentStepMeta(
        run_id=run.id,
        run_status=run.status,
        job_status=outcome.job_status,
        applied_count=run.applied_count,
        skipped_count=run.skipped_count,
        stuck_count=run.stuck_count,
        llm_calls=run.llm_calls,
        llm_calls_left=max(settings.llm_max_calls_per_run - run.llm_calls, 0),
        trace_id=outcome.trace_id,
        pacing=governor.next_pause(run.applied_count).as_dict(),
    )

    return outcome.response.model_copy(update={"meta": meta.model_dump(mode="json")})
