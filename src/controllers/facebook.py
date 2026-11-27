import os
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import or_, select

from src.database.companies import async_session_factory
from src.models.companies import (
    DesignImageGenerationModel,
    DesignImageModel,
    DoctorModel,
    FacebookPostScheduleModel,
    IdeasModel,
    TelegramPostReviewModel,
)
from src.schemas.companies import FacebookPostScheduleResponse
from src.services.telegram_reviews import PENDING


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def schedule_facebook_post(
    owner_id: UUID,
    generation_id: UUID,
    scheduled_for: datetime | Literal["now"],
    live: bool,
) -> FacebookPostScheduleResponse:
    now = datetime.now(timezone.utc)
    immediate = not isinstance(scheduled_for, datetime)

    if isinstance(scheduled_for, datetime):
        scheduled_for = _utc(scheduled_for)
        if scheduled_for < now + timedelta(minutes=10):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="schedule_for must be 'now' or at least 10 minutes in the future.",
            )
        if scheduled_for > now + timedelta(days=75):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="schedule_for must be within 75 days.",
            )
    else:
        scheduled_for = now

    async with async_session_factory() as session:
        doctor = await session.scalar(
            select(DoctorModel).where(DoctorModel.owner_id == owner_id)
        )
        if doctor is None:
            raise HTTPException(status_code=404, detail="Create a company profile first.")

        generation = await session.scalar(
            select(DesignImageGenerationModel).where(
                DesignImageGenerationModel.id == generation_id,
                DesignImageGenerationModel.company_id == doctor.id,
            )
        )
        if generation is None:
            raise HTTPException(status_code=404, detail="Design generation not found.")
        if not generation.stored:
            raise HTTPException(
                status_code=409,
                detail="Store the design first; only approved designs can be posted.",
            )

        # One live flow per approved design: blocked when the design was
        # already sent to Facebook OR is already waiting for Telegram
        # review. Without this guard, every repeat call posted/scheduled
        # the same image again. Previews (live=false) stay unlimited.
        if live:
            already = await session.scalar(
                select(FacebookPostScheduleModel).where(
                    FacebookPostScheduleModel.generation_id == generation.id,
                    or_(
                        FacebookPostScheduleModel.facebook_post_id.is_not(None),
                        FacebookPostScheduleModel.status == "awaiting_review",
                    ),
                )
            )
            if already is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This design was already sent to Facebook or is "
                        "awaiting Telegram review "
                        f"(status: {already.status}, scheduled_for: "
                        f"{already.scheduled_for}). Duplicate live posting is "
                        "blocked; previews (live=false) stay available."
                    ),
                )

        image = await session.scalar(
            select(DesignImageModel).where(
                DesignImageModel.ideas_id == generation.ideas_id,
                DesignImageModel.prompt_index == generation.prompt_index,
            )
        )
        ideas = await session.scalar(
            select(IdeasModel).where(IdeasModel.id == generation.ideas_id)
        )
        if image is None or ideas is None:
            raise HTTPException(status_code=404, detail="Stored design or content batch not found.")
        if generation.prompt_index >= len(ideas.captions):
            raise HTTPException(status_code=404, detail="No caption exists for this design index.")

        caption = ideas.captions[generation.prompt_index].strip()
        if not caption:
            raise HTTPException(status_code=422, detail="The design caption is empty.")

    schedule_id = uuid4()
    facebook_post_id: str | None = None
    result_status = "preview"

    if live and not immediate:
        # Telegram review flow: scheduled posts stay LOCAL at schedule time.
        # Nothing is sent to Facebook here; at the due time the review
        # worker sends the image and caption to Telegram, and only an
        # explicit approval publishes. Until then the row waits in
        # awaiting_review.
        result_status = "awaiting_review"

    elif live:
        page_id = os.getenv("FACEBOOK_PAGE_ID")
        access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
        if not page_id or not access_token:
            raise HTTPException(
                status_code=500,
                detail="FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN must be configured.",
            )

        payload = {
            "url": image.file_path,
            "message": caption,
            "access_token": access_token,
            "published": "true",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://graph.facebook.com/v22.0/{page_id}/photos",
                data=payload,
            )
        if response.status_code >= 400:
            try:
                error_detail = response.json()
            except Exception:
                error_detail = {"error": response.text}
            raise HTTPException(status_code=502, detail={"facebook_error": error_detail})

        response_data = response.json()
        facebook_post_id = response_data.get("post_id") or response_data.get("id")
        result_status = "published"

    async with async_session_factory() as session:
        session.add(
            FacebookPostScheduleModel(
                id=schedule_id,
                owner_id=owner_id,
                company_id=doctor.id,
                ideas_id=generation.ideas_id,
                generation_id=generation.id,
                caption=caption,
                image_url=image.file_path,
                scheduled_for=scheduled_for,
                facebook_post_id=facebook_post_id,
                status=result_status,
            )
        )
        await session.flush()  # insert the schedule before its review row (FK order)
        if result_status == "awaiting_review":
            # Same transaction: the schedule and its review row exist
            # together or not at all.
            session.add(
                TelegramPostReviewModel(
                    owner_id=owner_id,
                    schedule_id=schedule_id,
                    generation_id=generation.id,
                    status=PENDING,
                )
            )
        await session.commit()

    return FacebookPostScheduleResponse(
        schedule_id=schedule_id,
        generation_id=generation.id,
        image_url=image.file_path,
        caption=caption,
        scheduled_for=scheduled_for,
        live=live,
        status=result_status,
        facebook_post_id=facebook_post_id,
    )