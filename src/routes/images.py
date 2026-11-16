from uuid import UUID

from fastapi import APIRouter

from src.controllers.images import generate_design_image, store_generated_design_image
from src.jwt.auth import CurrentUser
from src.schemas.companies import DesignImageGenerationResponse, DesignImageResponse


router = APIRouter()


@router.post("/design-images/generate", response_model=DesignImageGenerationResponse)
async def generate_design_image_route(
    current_user: CurrentUser,
) -> DesignImageGenerationResponse:
    return await generate_design_image(owner_id=current_user.id)


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
