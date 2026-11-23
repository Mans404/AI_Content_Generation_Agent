from uuid import UUID

from fastapi import APIRouter

from src.controllers.images import (
    generate_all_design_images,
    regenerate_design_image,
    store_generated_design_image,
)
from src.controllers.facebook import schedule_facebook_post
from src.jwt.auth import CurrentUser
from src.schemas.companies import (
    DesignImageBatchGenerationResponse,
    DesignImageGenerationResponse,
    DesignImageRegenerateRequest,
    DesignImageResponse,
    FacebookPostScheduleRequest,
    FacebookPostScheduleResponse,
)

router = APIRouter()


@router.post(
    "/facebook-posts/schedule",
    response_model=FacebookPostScheduleResponse,
)
async def schedule_facebook_post_route(
    payload: FacebookPostScheduleRequest,
    current_user: CurrentUser,
) -> FacebookPostScheduleResponse:
    schedule_for = payload.scheduled_for or payload.schedule_for
    return await schedule_facebook_post(
        owner_id=current_user.id,
        generation_id=payload.generation_id,
        scheduled_for=schedule_for,
        live=payload.live,
    )


@router.post(
    "/design-images/generate-all",
    response_model=DesignImageBatchGenerationResponse,
)
async def generate_all_design_images_route(
    current_user: CurrentUser,
) -> DesignImageBatchGenerationResponse:
    return await generate_all_design_images(owner_id=current_user.id)


@router.post(
    "/design-images/{generation_id}/regenerate",
    response_model=DesignImageGenerationResponse,
)
async def regenerate_design_image_route(
    generation_id: UUID,
    current_user: CurrentUser,
    payload: DesignImageRegenerateRequest | None = None,
) -> DesignImageGenerationResponse:
    return await regenerate_design_image(
        owner_id=current_user.id,
        generation_id=generation_id,
        feedback=payload.feedback if payload else None,
    )


@router.post(
    "/design-images/{generation_id}/store",
    response_model=DesignImageResponse,
)
async def store_generated_design_image_route(
    generation_id: UUID,
    current_user: CurrentUser,
) -> DesignImageResponse:
    return await store_generated_design_image(
        owner_id=current_user.id,
        generation_id=generation_id,
    )