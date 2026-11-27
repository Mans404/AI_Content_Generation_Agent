"""Autopilot runner: executes one queued run, step by step.

Order: plan -> design prompts -> captions -> images (limit=N) -> store ->
schedule. Every post is scheduled with live=True and an explicit future
datetime, so the existing flow only creates awaiting_review rows and the
Telegram review decides; this module never publishes and never passes
"now". The six step functions are injected (default_steps imports the
real controllers only when called), so tests run with fakes.

Failure rules: a step that fails before any image is paid ends the run as
failed (reservation released). An image batch that raised something other
than "no image could be generated", and any run found "running" at worker
start, becomes needs_attention: a paid call may have happened, so nothing
is retried and the reservation stays until the user decides.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, NamedTuple
from uuid import UUID

from sqlalchemy import select, update

from src.database.companies import async_session_factory
from src.models.companies import (
    AutopilotRunModel as Run,
    AutopilotRunPostModel as Post,
    IdeasModel,
)
from src.services import autopilot_state as st

logger = logging.getLogger(__name__)

POLL_SECONDS = 5.0
SCHEDULE_MIN_LEAD = timedelta(minutes=10)


class Steps(NamedTuple):
    plan: Callable[..., Any]
    prompts: Callable[..., Any]
    captions: Callable[..., Any]
    images: Callable[..., Any]
    store: Callable[..., Any]
    schedule: Callable[..., Any]


def default_steps() -> Steps:
    from src.controllers.content import (
        generate_captions,
        start_design_prompt_generation,
        start_planning,
    )
    from src.controllers.facebook import schedule_facebook_post
    from src.controllers.images import (
        generate_all_design_images,
        store_generated_design_image,
    )

    return Steps(
        start_planning,
        start_design_prompt_generation,
        generate_captions,
        generate_all_design_images,
        store_generated_design_image,
        schedule_facebook_post,
    )


def _status_code(exc: BaseException) -> int | None:
    return getattr(exc, "status_code", None)


def _why(exc: BaseException) -> str:
    detail = getattr(exc, "detail", None) or str(exc)
    return f"{type(exc).__name__}: {detail}"[:300] if detail else type(exc).__name__


async def _load(run_id: UUID):
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        posts = (await session.execute(
            select(Post).where(Post.run_id == run_id).order_by(Post.position))).scalars().all()
        return run, list(posts)

async def _latest_ideas_id(company_id: UUID) -> UUID | None:
    async with async_session_factory() as session:
        return await session.scalar(
            select(IdeasModel.id).where(IdeasModel.company_id == company_id)
            .order_by(IdeasModel.created_at.desc()).limit(1))


async def _ideas_count(ideas_id: UUID) -> int:
    async with async_session_factory() as session:
        row = await session.get(IdeasModel, ideas_id)
        return len(row.ideas) if row is not None else 0


async def _active(run_id: UUID) -> bool:
    run, _ = await _load(run_id)
    return run is not None and run.status == "running"


async def recover_interrupted() -> int:
    """Run once at worker start: a run still 'running' was cut off mid-step."""
    async with async_session_factory() as session:
        ids = (await session.execute(
            select(Run.id).where(Run.status == "running"))).scalars().all()
    count = 0
    for run_id in ids:
        if await st.finish_run(run_id, "needs_attention", "interrupted by a restart"):
            count += 1
    return count


async def _fail(run_id: UUID, why: str) -> None:
    logger.error("autopilot run %s failed: %s", run_id, why)
    await st.finish_run(run_id, "failed", why)


async def _park(run_id: UUID, why: str) -> None:
    logger.error("autopilot run %s needs attention: %s", run_id, why)
    await st.finish_run(run_id, "needs_attention", why)


async def _same_batch(run: Run) -> bool:
    return await _latest_ideas_id(run.company_id) == run.ideas_id

async def _text_steps(run_id: UUID, steps: Steps) -> bool:
    """plan, prompts, captions. Returns False when the run ended or stopped."""
    run, _ = await _load(run_id)
    owner = run.owner_id
    if run.stage == "created":
        try:
            await steps.plan(owner)
        except Exception as exc:
            await _fail(run_id, "planning failed: " + _why(exc))
            return False
        ideas_id = await _latest_ideas_id(run.company_id)
        if ideas_id is None or not await st.set_ideas_id(run_id, ideas_id):
            await _fail(run_id, "planning produced no content batch")
            return False
        if await _ideas_count(ideas_id) < run.planned_posts:
            await _fail(run_id, "the plan has fewer ideas than posts")
            return False
        await st.advance_stage(run_id, "created", "planned")
    for stage, nxt, call, label in (
        ("planned", "prompts", steps.prompts, "design prompts"),
        ("prompts", "captions", steps.captions, "captions"),
    ):
        if not await _active(run_id):
            return False
        run, _ = await _load(run_id)
        if run.stage != stage:
            continue
        if not await _same_batch(run):
            await _fail(run_id, "the content batch changed during the run")
            return False
        try:
            await call(owner)
        except Exception as exc:
            await _fail(run_id, f"{label} failed: " + _why(exc))
            return False
        await st.advance_stage(run_id, stage, nxt)
    return True

async def _image_step(run_id: UUID, steps: Steps) -> bool:
    run, posts = await _load(run_id)
    if run.stage != "captions":
        return True
    if not await _same_batch(run):
        await _fail(run_id, "the content batch changed during the run")
        return False
    async with async_session_factory() as session:
        await session.execute(
            update(Post).where(Post.run_id == run_id, Post.image_state == "pending")
            .values(image_state="generating"))
        await session.commit()
    try:
        result = await steps.images(run.owner_id, limit=run.planned_posts)
    except Exception as exc:
        if _status_code(exc) == 502:  # nothing was generated
            for p in posts:
                await st.mark_image_failed(run_id, p.position, "no image was generated")
            await _fail(run_id, "no image could be generated")
        else:
            await _park(run_id, "image step crashed: " + _why(exc))
        return False
    made = {g.prompt_index: g.generation_id for g in result.generations}
    for p in posts:
        if p.position in made:
            await st.record_image_generated(run_id, p.position, made[p.position])
        else:
            await st.mark_image_failed(run_id, p.position, "image generation failed")
    await st.advance_stage(run_id, "captions", "images")
    return True


def _future(value: datetime, now: datetime) -> bool:
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value >= now + SCHEDULE_MIN_LEAD)

async def _store_and_schedule(run_id: UUID, steps: Steps) -> None:
    run, posts = await _load(run_id)
    if run.stage == "images":
        for p in posts:
            if p.image_state != "done" or p.post_state != "pending":
                continue
            try:
                await steps.store(run.owner_id, p.generation_id)
            except Exception as exc:
                logger.exception("autopilot run %s: store failed for post %s", run_id, p.position)
                await st.mark_post(run_id, p.position, "pending", "failed",

                                   "store failed: " + _why(exc))
        await st.advance_stage(run_id, "images", "stored")
    if not await _active(run_id):
        return
    run, posts = await _load(run_id)
    if run.stage != "stored":
        return
    for p in posts:
        if p.post_state != "pending" or p.image_state != "done":
            continue
        when = p.scheduled_for
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if not _future(when, datetime.now(timezone.utc)):
            await st.mark_post(run_id, p.position, "pending", "slot_expired",
                               "the time passed while images were generated")
            continue
        try:
            # live=True with a future datetime: awaiting_review only, never
            # a direct publish. Never "now".
            sched = await steps.schedule(run.owner_id, p.generation_id, when, True)
        except Exception as exc:
            logger.exception("autopilot run %s: schedule failed for post %s", run_id, p.position)
            state = "slot_expired" if _status_code(exc) == 422 else "failed"
            await st.mark_post(run_id, p.position, "pending", state, _why(exc))
            continue
        await st.mark_post(run_id, p.position, "pending", "scheduled",
                           schedule_id=getattr(sched, "schedule_id", None))
    await st.advance_stage(run_id, "stored", "scheduled")


async def process_run(run_id: UUID, steps: Steps | None = None) -> str:
    """Run one claimed (status running) run to its end. Returns the final status."""
    steps = steps or default_steps()
    try:
        if not await _text_steps(run_id, steps):
            return (await _load(run_id))[0].status
        if not await _active(run_id):
            return (await _load(run_id))[0].status
        if not await _image_step(run_id, steps):
            return (await _load(run_id))[0].status
        if await _active(run_id):
            await _store_and_schedule(run_id, steps)
        run, posts = await _load(run_id)
        if run.status != "running":
            return run.status
        ok = sum(1 for p in posts if p.post_state == "scheduled")
        final = "completed" if ok == len(posts) else "partial" if ok else "failed"
        await st.finish_run(run_id, final, None if final == "completed"
                            else f"{ok} of {len(posts)} posts scheduled")
        return final
    except Exception as exc:  # unexpected: a paid step may have run
        logger.exception("autopilot run %s crashed", run_id)
        await st.finish_run(run_id, "needs_attention", "crashed: " + type(exc).__name__)
        return "needs_attention"


async def run_loop(stop: asyncio.Event, steps: Steps | None = None,
                   poll: float = POLL_SECONDS) -> None:
    """Claim and process queued runs one at a time until stop is set."""
    while not stop.is_set():
        run_id = await st.claim_run()
        if run_id is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll)
            except asyncio.TimeoutError:
                pass
            continue
        await process_run(run_id, steps)