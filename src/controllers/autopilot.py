"""Controllers for the autopilot routes. They only read and write run
state; the worker does the paid work. Nothing here pays, and nothing here
publishes: reschedule goes through the same schedule function with
live=True and a future datetime, so it only creates awaiting_review rows.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update

from src.database.companies import async_session_factory
from src.models.companies import (
    AutopilotRunModel as Run,
    AutopilotRunPostModel as Post,
    DesignImageGenerationModel,
    DesignImageModel,
    IdeasModel,
    TelegramPostReviewModel,
)
from src.schemas.autopilot import (
    AutopilotPostStatus,
    AutopilotPreviewResponse,
    AutopilotRunResponse,
    AutopilotRunStatus,
    AutopilotRunSummary,
)
from src.services import autopilot_state as st

HTTP_STATUS = {
    "invalid_times": 422,
    "invalid_key": 422,
    "no_company": 404,
    "key_reused": 409,
    "active_run": 409,
    "too_many_posts": 422,
    "budget": 409,
}
FINISHED = ("completed", "partial", "failed")


def _http(exc: st.AutopilotError) -> HTTPException:
    detail = {"code": exc.code, "detail": exc.detail}
    if exc.run_id is not None:
        detail["run_id"] = str(exc.run_id)
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 400), detail=detail)


async def preview_autopilot_run(owner_id: UUID, times) -> AutopilotPreviewResponse:
    return AutopilotPreviewResponse(**await st.preview_run(owner_id, times))


async def create_autopilot_run(owner_id: UUID, times, key: str) -> AutopilotRunResponse:
    try:
        result = await st.create_run(owner_id, key, times)
    except st.AutopilotError as exc:
        raise _http(exc) from None
    async with async_session_factory() as session:
        run = await session.get(Run, result.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Autopilot run not found.")
    return AutopilotRunResponse(
        run_id=result.run_id, status=run.status, created=result.created,
        planned_posts=result.planned_posts, planned_images=result.planned_images)


async def _owned_run(session, owner_id: UUID, run_id: UUID) -> Run:
    run = await session.scalar(select(Run).where(Run.id == run_id, Run.owner_id == owner_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Autopilot run not found.")
    return run

async def get_autopilot_run(owner_id: UUID, run_id: UUID) -> AutopilotRunStatus:
    async with async_session_factory() as session:
        run = await _owned_run(session, owner_id, run_id)
        posts = (await session.execute(
            select(Post).where(Post.run_id == run_id).order_by(Post.position))).scalars().all()
        ids = [p.schedule_id for p in posts if p.schedule_id is not None]
        reviews = {}
        if ids:
            rows = await session.execute(
                select(TelegramPostReviewModel.schedule_id, TelegramPostReviewModel.status)
                .where(TelegramPostReviewModel.schedule_id.in_(ids)))
            reviews = {sid: s for sid, s in rows.all()}
        media = await _post_media(
            session, [p.generation_id for p in posts if p.generation_id is not None])
    return AutopilotRunStatus(
        run_id=run.id, status=run.status, stage=run.stage,
        planned_posts=run.planned_posts, planned_images=run.planned_images,
        last_error=run.last_error, created_at=run.created_at,
        posts=[AutopilotPostStatus(
            position=p.position, scheduled_for=p.scheduled_for, image_state=p.image_state,
            post_state=p.post_state, error=p.error, generation_id=p.generation_id,
            schedule_id=p.schedule_id, review_status=reviews.get(p.schedule_id) if p.schedule_id is not None else None,
            image_url=media.get(p.generation_id, (None, None))[0],
            caption=media.get(p.generation_id, (None, None))[1]) for p in posts],
        budget=await st.month_balance(owner_id))


async def cancel_autopilot_run(owner_id: UUID, run_id: UUID) -> AutopilotRunStatus:
    async with async_session_factory() as session:
        run = await _owned_run(session, owner_id, run_id)
        if run.status == "running":
            raise HTTPException(
                status_code=409,
                detail="The run is in progress and cannot be cancelled mid-way "
                       "(images may already be paid). Try again when it finishes.")
    if not await st.cancel_idle_run(run_id):
        raise HTTPException(status_code=409, detail="The run is no longer cancellable.")
    return await get_autopilot_run(owner_id, run_id)

async def reschedule_autopilot_post(owner_id: UUID, run_id: UUID, position: int,
                                    when: datetime, schedule=None) -> AutopilotPostStatus:
    try:
        when_utc = st.normalize_times([when], datetime.now(timezone.utc))[0]
    except st.AutopilotError as exc:
        raise _http(exc) from None
    async with async_session_factory() as session:
        run = await _owned_run(session, owner_id, run_id)
        if run.status not in FINISHED:
            raise HTTPException(status_code=409, detail="Wait until the run has finished.")
        post = await session.scalar(
            select(Post).where(Post.run_id == run_id, Post.position == position))
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found.")
        if post.post_state != "slot_expired" or post.generation_id is None:
            raise HTTPException(status_code=409, detail="Only a post whose time expired can be rescheduled.")
        generation_id = post.generation_id
    if schedule is None:
        from src.controllers.facebook import schedule_facebook_post as schedule
    # live=True with a future datetime: awaiting_review only, never a direct publish.
    sched = await schedule(owner_id, generation_id, when_utc, True)
    async with async_session_factory() as session:
        await session.execute(
            update(Post).where(Post.run_id == run_id, Post.position == position,
                               Post.post_state == "slot_expired")
            .values(scheduled_for=when_utc, post_state="scheduled", error=None,
                    schedule_id=sched.schedule_id))
        await session.commit()
        post = await session.scalar(
            select(Post).where(Post.run_id == run_id, Post.position == position))
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    return AutopilotPostStatus(
        position=post.position, scheduled_for=post.scheduled_for, image_state=post.image_state,
        post_state=post.post_state, error=post.error, generation_id=post.generation_id,
        schedule_id=post.schedule_id)

async def list_autopilot_runs(owner_id: UUID, limit: int = 20) -> list[AutopilotRunSummary]:
    async with async_session_factory() as session:
        runs = (await session.execute(
            select(Run).where(Run.owner_id == owner_id)
            .order_by(Run.created_at.desc()).limit(limit))).scalars().all()
    return [AutopilotRunSummary(
        run_id=r.id, status=r.status, stage=r.stage, planned_posts=r.planned_posts,
        planned_images=r.planned_images, last_error=r.last_error, created_at=r.created_at)
        for r in runs]

async def _post_media(session, generation_ids) -> dict:
    """generation_id -> (image_url, caption), from the same rows the schedule
    step reads: the stored design image and the batch caption. A design that
    is not stored yet has no image_url."""
    if not generation_ids:
        return {}
    gens = (await session.execute(
        select(DesignImageGenerationModel).where(
            DesignImageGenerationModel.id.in_(generation_ids)))).scalars().all()
    ideas_ids = list({g.ideas_id for g in gens})
    ideas = {i.id: i for i in (await session.execute(
        select(IdeasModel).where(IdeasModel.id.in_(ideas_ids)))).scalars().all()}
    images = {(i.ideas_id, i.prompt_index): i.file_path for i in (await session.execute(
        select(DesignImageModel).where(
            DesignImageModel.ideas_id.in_(ideas_ids)))).scalars().all()}
    result = {}
    for g in gens:
        batch = ideas.get(g.ideas_id)
        caption = None
        if batch is not None and g.prompt_index < len(batch.captions):
            caption = batch.captions[g.prompt_index]
        result[g.id] = (images.get((g.ideas_id, g.prompt_index)), caption)
    return result