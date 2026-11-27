from fastapi import APIRouter

from src.controllers.content import (
    generate_captions,
    start_design_prompt_generation,
    start_planning,
)
from src.jwt.auth import CurrentUser
from src.schemas.companies import (
    CaptionsResponse,
    DesignPromptsResponse,
    StartPlanningResponse,
)


router = APIRouter()


@router.post("/start_planning", response_model=StartPlanningResponse)
async def start_planning_route(
    current_user: CurrentUser,
) -> StartPlanningResponse:
    return await start_planning(owner_id=current_user.id)


@router.post("/design-prompts", response_model=DesignPromptsResponse)
async def start_design_prompt_generation_route(
    current_user: CurrentUser,
) -> DesignPromptsResponse:
    result = await start_design_prompt_generation(owner_id=current_user.id)
    return DesignPromptsResponse(design_prompts=result.design_prompts)


@router.post("/captions", response_model=CaptionsResponse)
async def generate_captions_route(
    current_user: CurrentUser,
) -> CaptionsResponse:
    result = await generate_captions(owner_id=current_user.id)
    return CaptionsResponse(captions=result.captions)
