import logging
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from src.agents.design_image_agent import design_image_agent
from src.database.companies import async_session_factory
from src.models.companies import (
    DesignImageGenerationModel,
    DesignImageModel,
    DoctorModel,
    IdeasModel,
)
from src.schemas.companies import (
    DesignImageGenerationResponse,
    DesignImageResponse,
)
from src.services.storage import DESIGN_IMAGES_BUCKET, supabase_storage

logger = logging.getLogger(__name__)


def _temporary_path(generation_id: UUID, extension: str) -> str:
    return f"pending/{generation_id}.{extension}"


async def generate_design_image(owner_id: UUID) -> DesignImageGenerationResponse:
    async with async_session_factory() as session:
        doctor = await session.scalar(
            select(DoctorModel).where(DoctorModel.owner_id == owner_id)
        )
        if doctor is None:
            raise HTTPException(status_code=404, detail="Create a company profile first.")

        ideas = await session.scalar(
            select(IdeasModel)
            .where(IdeasModel.company_id == doctor.id)
            .order_by(IdeasModel.created_at.desc())
            .with_for_update()
        )
        if ideas is None or not ideas.design_prompts:
            raise HTTPException(
                status_code=404,
                detail="Generate design prompts before requesting design images.",
            )

        stored_count = await session.scalar(
            select(func.count(DesignImageModel.id)).where(
                DesignImageModel.ideas_id == ideas.id
            )
        )
        prompt_index = int(stored_count or 0)
        if prompt_index >= len(ideas.design_prompts):
            raise HTTPException(status_code=404, detail="No more design images are available.")

        generation = await session.scalar(
            select(DesignImageGenerationModel)
            .where(
                DesignImageGenerationModel.ideas_id == ideas.id,
                DesignImageGenerationModel.prompt_index == prompt_index,
            )
            .with_for_update()
        )
        if generation is None:
            generated = await design_image_agent.generate(ideas.design_prompts[prompt_index])
            generation = DesignImageGenerationModel(
                id=uuid4(),
                company_id=doctor.id,
                ideas_id=ideas.id,
                prompt_index=prompt_index,
                file_path=_temporary_path(uuid4(), generated.extension),
            )
            try:
                await supabase_storage.upload(
                    DESIGN_IMAGES_BUCKET,
                    generation.file_path,
                    generated.data,
                    f"image/{'jpeg' if generated.extension == 'jpeg' else generated.extension}",
                )
                session.add(generation)
                await session.commit()
            except Exception:
                try:
                    await supabase_storage.delete(
                        DESIGN_IMAGES_BUCKET, generation.file_path
                    )
                except Exception:
                    logger.warning(
                        "Could not remove failed temporary design image %s",
                        generation.file_path,
                        exc_info=True,
                    )
                raise

        image_url = supabase_storage.public_url(
            DESIGN_IMAGES_BUCKET, generation.file_path
        )
        return DesignImageGenerationResponse(
            generation_id=generation.id,
            image_url=image_url,
            prompt_index=generation.prompt_index,
            remaining_prompts=len(ideas.design_prompts) - generation.prompt_index - 1,
        )


async def store_generated_design_image(
    owner_id: UUID,
    generation_id: UUID,
) -> DesignImageResponse:
    async with async_session_factory() as session:
        doctor = await session.scalar(
            select(DoctorModel).where(DoctorModel.owner_id == owner_id)
        )
        if doctor is None:
            raise HTTPException(status_code=404, detail="Create a company profile first.")

        generation = await session.scalar(
            select(DesignImageGenerationModel)
            .where(
                DesignImageGenerationModel.id == generation_id,
                DesignImageGenerationModel.company_id == doctor.id,
            )
            .with_for_update()
        )
        if generation is None:
            raise HTTPException(status_code=404, detail="Design generation not found.")

        ideas = await session.scalar(
            select(IdeasModel).where(IdeasModel.id == generation.ideas_id)
        )
        if ideas is None:
            raise HTTPException(status_code=404, detail="Design batch not found.")

        if generation.stored:
            image = await session.scalar(
                select(DesignImageModel).where(
                    DesignImageModel.ideas_id == generation.ideas_id,
                    DesignImageModel.prompt_index == generation.prompt_index,
                )
            )
            if image is None:
                raise RuntimeError("Stored design generation has no design image record.")
            image_url = image.file_path
        else:
            extension = PurePosixPath(generation.file_path).suffix
            final_path = f"{generation.id}{extension}"
            await supabase_storage.move(
                DESIGN_IMAGES_BUCKET, generation.file_path, final_path
            )
            image_url = supabase_storage.public_url(DESIGN_IMAGES_BUCKET, final_path)
            generation.file_path = final_path
            generation.stored = True
            session.add(
                DesignImageModel(
                    company_id=generation.company_id,
                    ideas_id=generation.ideas_id,
                    prompt_index=generation.prompt_index,
                    file_path=image_url,
                )
            )
            await session.commit()

    return DesignImageResponse(
        image_url=image_url,
        prompt_index=generation.prompt_index,
        remaining_prompts=len(ideas.design_prompts) - generation.prompt_index - 1,
    )
