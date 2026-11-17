import asyncio
import logging
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.agents.design_image_agent import GeneratedImage, design_image_agent
from src.database.companies import async_session_factory
from src.models.companies import (
    DesignImageGenerationModel,
    DesignImageModel,
    DoctorModel,
    IdeasModel,
)
from src.schemas.companies import (
    DesignImageBatchGenerationResponse,
    DesignImageGenerationResponse,
    DesignImageResponse,
)
from src.services.storage import DESIGN_IMAGES_BUCKET, supabase_storage

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

# In-process guards against double clicks / concurrent requests for the same key.
# (With multiple workers, the unique constraint on (ideas_id, prompt_index) is the
# real protection; see the note at the end.)
_locks: dict[UUID, asyncio.Lock] = {}


def _lock_for(key: UUID) -> asyncio.Lock:
    return _locks.setdefault(key, asyncio.Lock())


@dataclass(frozen=True)
class _Context:
    company_id: UUID
    ideas_id: UUID
    prompts: list[str]


# ---------------------------------------------------------------- helpers


def _temporary_path(generation_id: UUID, extension: str) -> str:
    return f"pending/{generation_id}.{extension}"


def _content_type(extension: str) -> str:
    return _CONTENT_TYPES.get(extension, "image/png")


async def _safe_delete(path: str) -> None:
    try:
        await supabase_storage.delete(DESIGN_IMAGES_BUCKET, path)
    except Exception:
        logger.warning("Could not remove design image %s", path, exc_info=True)


async def _get_doctor(session, owner_id: UUID) -> DoctorModel:
    doctor = await session.scalar(
        select(DoctorModel).where(DoctorModel.owner_id == owner_id)
    )
    if doctor is None:
        raise HTTPException(status_code=404, detail="Create a company profile first.")
    return doctor


async def _load_context(owner_id: UUID) -> _Context:
    """Short read-only session: no lock is held while images are generated."""
    async with async_session_factory() as session:
        doctor = await _get_doctor(session, owner_id)
        ideas = await session.scalar(
            select(IdeasModel)
            .where(IdeasModel.company_id == doctor.id)
            .order_by(IdeasModel.created_at.desc())
        )
        if ideas is None or not ideas.design_prompts:
            raise HTTPException(
                status_code=404,
                detail="Generate design prompts before requesting design images.",
            )
        return _Context(
            company_id=doctor.id,
            ideas_id=ideas.id,
            prompts=list(ideas.design_prompts),
        )


async def _load_generations(ideas_id: UUID) -> dict[int, DesignImageGenerationModel]:
    async with async_session_factory() as session:
        rows = await session.scalars(
            select(DesignImageGenerationModel).where(
                DesignImageGenerationModel.ideas_id == ideas_id
            )
        )
        return {row.prompt_index: row for row in rows}


def _to_response(
    generation: DesignImageGenerationModel, total_prompts: int
) -> DesignImageGenerationResponse:
    return DesignImageGenerationResponse(
        generation_id=generation.id,
        image_url=supabase_storage.public_url(DESIGN_IMAGES_BUCKET, generation.file_path),
        prompt_index=generation.prompt_index,
        remaining_prompts=total_prompts - generation.prompt_index - 1,
    )


async def _persist_new_generations(
    ctx: _Context,
    items: list[tuple[int, GeneratedImage]],
) -> dict[int, DesignImageGenerationModel]:
    """Upload all images in parallel, then insert all rows in ONE commit."""
    prepared = []
    for prompt_index, generated in items:
        generation_id = uuid4()
        prepared.append(
            (
                prompt_index,
                generation_id,
                _temporary_path(generation_id, generated.extension),
                generated,
            )
        )

    upload_results = await asyncio.gather(
        *(
            supabase_storage.upload(
                DESIGN_IMAGES_BUCKET,
                path,
                generated.data,
                _content_type(generated.extension),
            )
            for _, _, path, generated in prepared
        ),
        return_exceptions=True,
    )

    uploaded = []
    for (prompt_index, generation_id, path, _), result in zip(prepared, upload_results):
        if isinstance(result, BaseException):
            logger.error(
                "Upload failed for design image %s", prompt_index, exc_info=result
            )
        else:
            uploaded.append((prompt_index, generation_id, path))

    if not uploaded:
        return await _load_generations(ctx.ideas_id)

    uploaded_paths = [path for _, _, path in uploaded]
    try:
        async with async_session_factory() as session:
            session.add_all(
                DesignImageGenerationModel(
                    id=generation_id,
                    company_id=ctx.company_id,
                    ideas_id=ctx.ideas_id,
                    prompt_index=prompt_index,
                    file_path=path,
                )
                for prompt_index, generation_id, path in uploaded
            )
            await session.commit()
    except IntegrityError:
        # A concurrent request already saved some of these indexes.
        logger.warning("Concurrent design image generation detected; discarding duplicates.")
        await asyncio.gather(*(_safe_delete(path) for path in uploaded_paths))
    except Exception:
        await asyncio.gather(*(_safe_delete(path) for path in uploaded_paths))
        raise

    return await _load_generations(ctx.ideas_id)


# ------------------------------------------------------------- operations


async def generate_all_design_images(
    owner_id: UUID,
) -> DesignImageBatchGenerationResponse:
    """Generate every missing design. Safe to call again: only missing / previously
    failed indexes are generated, existing ones are returned as they are."""
    ctx = await _load_context(owner_id)
    total = len(ctx.prompts)

    async with _lock_for(ctx.ideas_id):
        generations = await _load_generations(ctx.ideas_id)
        missing = [index for index in range(total) if index not in generations]

        if missing:
            results = await design_image_agent.generate_many(
                [ctx.prompts[index] for index in missing]
            )
            succeeded: list[tuple[int, GeneratedImage]] = []
            for prompt_index, result in zip(missing, results):
                if isinstance(result, BaseException):
                    logger.error(
                        "Design image %s failed to generate", prompt_index, exc_info=result
                    )
                else:
                    succeeded.append((prompt_index, result))

            if succeeded:
                generations = await _persist_new_generations(ctx, succeeded)

            if not generations:
                raise HTTPException(
                    status_code=502,
                    detail="Could not generate design images. Please try again.",
                )

    return DesignImageBatchGenerationResponse(
        generations=[
            _to_response(generations[index], total) for index in sorted(generations)
        ]
    )


async def regenerate_design_image(
    owner_id: UUID,
    generation_id: UUID,
    feedback: str | None = None,
) -> DesignImageGenerationResponse:
    """Replace the image of one (not yet approved) design, optionally using the
    user's feedback. Human-in-the-loop: the user rejects one image and asks again."""
    async with async_session_factory() as session:
        doctor = await _get_doctor(session, owner_id)
        generation = await session.scalar(
            select(DesignImageGenerationModel).where(
                DesignImageGenerationModel.id == generation_id,
                DesignImageGenerationModel.company_id == doctor.id,
            )
        )
        if generation is None:
            raise HTTPException(status_code=404, detail="Design generation not found.")
        if generation.stored:
            raise HTTPException(
                status_code=409, detail="This design was already approved."
            )
        ideas = await session.scalar(
            select(IdeasModel).where(IdeasModel.id == generation.ideas_id)
        )
        if ideas is None or generation.prompt_index >= len(ideas.design_prompts):
            raise HTTPException(status_code=404, detail="Design prompt not found.")
        prompt = ideas.design_prompts[generation.prompt_index]
        prompt_index = generation.prompt_index
        total = len(ideas.design_prompts)

    if feedback and feedback.strip():
        prompt = f"{prompt}\n\nAdjustments requested by the user: {feedback.strip()}"

    async with _lock_for(generation_id):
        generated = await design_image_agent.generate(prompt)
        new_path = _temporary_path(uuid4(), generated.extension)
        await supabase_storage.upload(
            DESIGN_IMAGES_BUCKET,
            new_path,
            generated.data,
            _content_type(generated.extension),
        )

        try:
            async with async_session_factory() as session:
                generation = await session.scalar(
                    select(DesignImageGenerationModel)
                    .where(DesignImageGenerationModel.id == generation_id)
                    .with_for_update()
                )
                if generation is None or generation.stored:
                    raise HTTPException(
                        status_code=409,
                        detail="This design was approved while regenerating.",
                    )
                old_path = generation.file_path
                generation.file_path = new_path
                await session.commit()
        except Exception:
            await _safe_delete(new_path)
            raise

    await _safe_delete(old_path)

    return DesignImageGenerationResponse(
        generation_id=generation_id,
        image_url=supabase_storage.public_url(DESIGN_IMAGES_BUCKET, new_path),
        prompt_index=prompt_index,
        remaining_prompts=total - prompt_index - 1,
    )


async def store_generated_design_image(
    owner_id: UUID,
    generation_id: UUID,
) -> DesignImageResponse:
    """Approve one design: move it from pending/ to its final path. Idempotent."""
    async with async_session_factory() as session:
        doctor = await _get_doctor(session, owner_id)

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

        prompt_index = generation.prompt_index
        remaining = len(ideas.design_prompts) - prompt_index - 1

        if generation.stored:
            image = await session.scalar(
                select(DesignImageModel).where(
                    DesignImageModel.ideas_id == generation.ideas_id,
                    DesignImageModel.prompt_index == prompt_index,
                )
            )
            if image is None:
                raise RuntimeError("Stored design generation has no design image record.")
            image_url = image.file_path
        else:
            old_path = generation.file_path
            extension = PurePosixPath(old_path).suffix  # includes the dot
            final_path = f"{generation.id}{extension}"
            await supabase_storage.move(DESIGN_IMAGES_BUCKET, old_path, final_path)
            image_url = supabase_storage.public_url(DESIGN_IMAGES_BUCKET, final_path)
            try:
                generation.file_path = final_path
                generation.stored = True
                session.add(
                    DesignImageModel(
                        company_id=generation.company_id,
                        ideas_id=generation.ideas_id,
                        prompt_index=prompt_index,
                        file_path=image_url,
                    )
                )
                await session.commit()
            except Exception:
                # DB failed after the file was moved: put the file back.
                try:
                    await supabase_storage.move(DESIGN_IMAGES_BUCKET, final_path, old_path)
                except Exception:
                    logger.warning(
                        "Could not move %s back to %s", final_path, old_path, exc_info=True
                    )
                raise

    return DesignImageResponse(
        image_url=image_url,
        prompt_index=prompt_index,
        remaining_prompts=remaining,
    )