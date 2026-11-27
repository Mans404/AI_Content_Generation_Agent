from uuid import UUID

from fastapi import APIRouter, Query

from src.controllers.autopilot import (
    cancel_autopilot_run,
    create_autopilot_run,
    get_autopilot_run,
    list_autopilot_runs,
    preview_autopilot_run,
    reschedule_autopilot_post,
)
from src.jwt.auth import CurrentUser
from src.schemas.autopilot import (
    AutopilotPostStatus,
    AutopilotPreviewRequest,
    AutopilotPreviewResponse,
    AutopilotRescheduleRequest,
    AutopilotRunRequest,
    AutopilotRunResponse,
    AutopilotRunStatus,
    AutopilotRunSummary,
)

router = APIRouter()


@router.post("/autopilot/runs/dry-run", response_model=AutopilotPreviewResponse)
async def preview_autopilot_run_route(
    payload: AutopilotPreviewRequest,
    current_user: CurrentUser,
) -> AutopilotPreviewResponse:
    return await preview_autopilot_run(current_user.id, payload.scheduled_for)


@router.post("/autopilot/runs", response_model=AutopilotRunResponse, status_code=202)
async def create_autopilot_run_route(
    payload: AutopilotRunRequest,
    current_user: CurrentUser,
) -> AutopilotRunResponse:
    return await create_autopilot_run(
        current_user.id, payload.scheduled_for, payload.idempotency_key
    )


@router.get("/autopilot/runs/{run_id}", response_model=AutopilotRunStatus)
async def get_autopilot_run_route(
    run_id: UUID,
    current_user: CurrentUser,
) -> AutopilotRunStatus:
    return await get_autopilot_run(current_user.id, run_id)


@router.post("/autopilot/runs/{run_id}/cancel", response_model=AutopilotRunStatus)
async def cancel_autopilot_run_route(
    run_id: UUID,
    current_user: CurrentUser,
) -> AutopilotRunStatus:
    return await cancel_autopilot_run(current_user.id, run_id)


@router.post(
    "/autopilot/runs/{run_id}/posts/{position}/reschedule",
    response_model=AutopilotPostStatus,
)
async def reschedule_autopilot_post_route(
    run_id: UUID,
    position: int,
    payload: AutopilotRescheduleRequest,
    current_user: CurrentUser,
) -> AutopilotPostStatus:
    return await reschedule_autopilot_post(
        current_user.id, run_id, position, payload.scheduled_for
    )

@router.get("/autopilot/runs", response_model=list[AutopilotRunSummary])
async def list_autopilot_runs_route(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=50),
) -> list[AutopilotRunSummary]:
    return await list_autopilot_runs(current_user.id, limit)