from uuid import UUID

from fastapi import APIRouter

from src.controllers.images import (
    generate_all_design_images,
    regenerate_design_image,
    store_generated_design_image,
)
from src.jwt.auth import CurrentUser
from src.schemas.companies import (
    DesignImageBatchGenerationResponse,
    DesignImageGenerationResponse,
    DesignImageRegenerateRequest,
    DesignImageResponse,
)

router = APIRouter()


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