"""State transitions for the Telegram post-review flow.

claim_due_reviews locks due rows FOR UPDATE SKIP LOCKED on PostgreSQL
(one worker claims each row), a no-op on dialects without row locking
like SQLite. Each claim bumps attempts and returns a ClaimedReview
snapshot: the review id, the attempt number identifying that claim, the
image path read from the current generation in the same transaction (so
a regenerated image is what the next claim picks up), and the schedule
caption. Worker transitions (record_photo_progress,
mark_awaiting_approval, requeue_sending, mark_needs_attention) are
conditional UPDATEs bound to the expected status AND the claim's attempt
number, so a worker that lost its claim cannot move the row or overwrite
a newer state like approved/published. That fencing protects database
writes only; it cannot undo a network send already in flight, so
still_claimed runs right before sending to shrink that window, not
close it. Owner responses bind the owner and the current
telegram_message_id, so a stale button from an older image can never
move a re-sent review. Rows stuck in "sending" past STUCK_AFTER go to
needs_attention and are never auto-retried. Nothing here talks to
Telegram or Facebook.
"""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.database.companies import async_session_factory
from src.models.companies import (
    DesignImageGenerationModel,
    DesignImageModel,
    DoctorModel,
    FacebookPostScheduleModel,
    IdeasModel,
    TelegramPostReviewModel,
)

PENDING, SENDING, AWAITING = "pending", "sending", "awaiting_approval"
APPROVED, PUBLISHING, PUBLISHED = "approved", "publishing", "published"
REJECTED, FAILED, NEEDS_ATTENTION = "rejected", "failed", "needs_attention"
STUCK_AFTER = timedelta(minutes=10)
R, F = TelegramPostReviewModel, FacebookPostScheduleModel
D = DoctorModel
G = DesignImageGenerationModel


class ClaimedReview(NamedTuple):
    review_id: UUID
    attempt: int
    owner_id: UUID
    image_path: str
    caption: str


def _dup_schedule(exc: IntegrityError) -> bool:
    # True only for the unique(schedule_id) conflict, never FK/not-null errors
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate is not None:  # PostgreSQL: unique_violation on our constraint only
        diag = getattr(orig, "diag", None)
        return sqlstate == "23505" and "schedule_id" in (getattr(diag, "constraint_name", "") or "")
    return "UNIQUE constraint failed: telegram_post_reviews.schedule_id" in str(orig)


async def create_review(owner_id: UUID, schedule_id: UUID, generation_id: UUID) -> bool:
    """Add a pending review for a schedule; False if one already exists."""
    async with async_session_factory() as session:
        session.add(R(owner_id=owner_id, schedule_id=schedule_id,
                      generation_id=generation_id, status=PENDING))
        try:
            await session.commit()
            return True
        except IntegrityError as exc:
            if _dup_schedule(exc):
                return False
            raise


async def claim_due_reviews(owner_id: UUID, limit: int = 10) -> list[ClaimedReview]:
    """Claim one owner's due pending reviews; the sweep is owner-scoped too."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        await session.execute(
            update(R)
            .where(R.status == SENDING, R.owner_id == owner_id,
                   R.claimed_at < now - STUCK_AFTER)
            .values(status=NEEDS_ATTENTION,
                    last_error="stuck in sending; may already be on Telegram"))
        rows = (await session.execute(
            select(R, G.file_path.label("image_path"), F.caption.label("caption"))
            .join(F, F.id == R.schedule_id)
            .join(G, G.id == R.generation_id)
            .where(R.status == PENDING, R.owner_id == owner_id,
                   F.scheduled_for <= now)
            .order_by(F.scheduled_for).limit(limit)
            .with_for_update(of=R, skip_locked=True))).all()
        claims = []
        for row in rows:
            review = row[0]
            review.status, review.claimed_at = SENDING, now
            review.attempts += 1
            claims.append(
                ClaimedReview(review.id, review.attempts, review.owner_id,
                              row.image_path, row.caption))
        await session.commit()
        return claims


async def _transition(review_id: UUID, expect: str, to: str, *extra, **values) -> bool:
    async with async_session_factory() as session:
        matched = await session.scalar(
            update(R)
            .where(R.id == review_id, R.status == expect, *extra)
            .values(status=to, **values)
            .returning(R.id))
        await session.commit()
        # True only when the UPDATE matched a row: RETURNING hands the id
        # back from the database itself, so a committed row is never
        # reported lost, and no rowcount typing guesswork is needed
        return matched is not None


async def still_claimed(review_id: UUID, attempt: int) -> bool:
    # preflight read right before sending: catches a claim already lost.
    # A loss after the read is still possible, so this narrows the window
    # without closing it; the bound transitions above still protect the row.
    async with async_session_factory() as session:
        return await session.scalar(
            select(R.id).where(R.id == review_id, R.status == SENDING,
                               R.attempts == attempt)) is not None


async def record_photo_progress(
    review_id: UUID, attempt: int, telegram_message_id: str,
    image_path: str, caption: str,
) -> bool:
    # stays in sending, but stores the delivered photo's message id and the
    # exact content sent for review before anything else is sent, so a crash
    # mid-flow never loses track of it and a later publish can verify the
    # approved content has not changed
    return await _transition(review_id, SENDING, SENDING,
                             R.attempts == attempt,
                             telegram_message_id=telegram_message_id,
                             sent_image_path=image_path, sent_caption=caption)


async def mark_awaiting_approval(review_id: UUID, attempt: int, telegram_message_id: str) -> bool:
    # sending -> awaiting_approval, only while this claim still owns the row
    return await _transition(review_id, SENDING, AWAITING,
                             R.attempts == attempt,
                             telegram_message_id=telegram_message_id,
                             claimed_at=None, last_error=None)


async def mark_approved(review_id: UUID, owner_id: UUID, telegram_message_id: str) -> bool:
    # awaiting_approval -> approved, only via the current message's button
    return await _transition(
        review_id, AWAITING, APPROVED,
        R.owner_id == owner_id, R.telegram_message_id == telegram_message_id,
        responded_at=datetime.now(timezone.utc))


async def mark_rejected(review_id: UUID, owner_id: UUID, telegram_message_id: str) -> bool:
    # awaiting_approval -> rejected, only via the current message's button
    return await _transition(
        review_id, AWAITING, REJECTED,
        R.owner_id == owner_id, R.telegram_message_id == telegram_message_id,
        responded_at=datetime.now(timezone.utc))


async def requeue_rejected(review_id: UUID, generation_id: UUID) -> bool:
    # rejected -> pending, pointing at the regenerated image
    return await _transition(review_id, REJECTED, PENDING,
                             generation_id=generation_id,
                             telegram_message_id=None, claimed_at=None)


async def requeue_sending(review_id: UUID, attempt: int) -> bool:
    # sending -> pending after a send that never reached Telegram (retry);
    # False means the row moved on and this worker must stop touching it
    return await _transition(review_id, SENDING, PENDING,
                             R.attempts == attempt, claimed_at=None)


async def mark_needs_attention(review_id: UUID, attempt: int, reason: str) -> bool:
    # sending -> needs_attention; never auto-retried, needs a human look.
    # Bound to this claim so it can never overwrite approved/published rows.
    return await _transition(review_id, SENDING, NEEDS_ATTENTION,
                             R.attempts == attempt, last_error=reason[:1000])


class ApprovedReview(NamedTuple):
    review_id: UUID
    attempt: int
    owner_id: UUID
    schedule_id: UUID
    company_id: UUID
    image_path: str
    caption: str


async def claim_approved_reviews(owner_id: UUID, limit: int = 10) -> list[ApprovedReview]:
    """Claim one owner's approved reviews (approved -> publishing).

    Re-validated in the claim transaction; a row that fails goes to
    needs_attention, never to publishing: the schedule's owner must be
    this owner; the review's generation must be the schedule's own
    generation, not just any generation in the same company; the
    generation's company must be the schedule's company and belong to
    this owner (schema joins, not naming); and the current image path
    and caption must equal the content recorded when the review was
    sent (missing or changed content fails closed).
    Rows stuck in publishing past STUCK_AFTER go to needs_attention:
    the post may already be on Facebook, so they are never auto-retried.
    The attempt in each claim is its identity; fencing protects
    database transitions only, never an in-flight remote call. The
    publisher must post the claim's image_path/caption, never re-read
    the schedule or generation at send time; mark_review_published
    re-checks that equality in its commit transaction.
    """
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        await session.execute(
            update(R)
            .where(R.status == PUBLISHING, R.owner_id == owner_id,
                   R.claimed_at < now - STUCK_AFTER)
            .values(status=NEEDS_ATTENTION,
                    last_error="stuck in publishing; the post may already be on Facebook"))
        rows = (await session.execute(
            select(R,
                   G.file_path.label("image_path"),
                   F.caption.label("caption"),
                   F.company_id.label("sched_company"),
                   G.company_id.label("gen_company"),
                   F.owner_id.label("sched_owner"),
                   D.owner_id.label("co_owner"),
                   F.generation_id.label("sched_gen"))
            .join(F, F.id == R.schedule_id)
            .join(G, G.id == R.generation_id)
            .join(D, D.id == G.company_id)
            .where(R.status == APPROVED, R.owner_id == owner_id)
            .order_by(F.scheduled_for).limit(limit)
            .with_for_update(of=R, skip_locked=True))).all()
        claims = []
        for row in rows:
            review = row[0]
            if (row.sched_owner != owner_id or row.co_owner != owner_id
                    or review.generation_id != row.sched_gen
                    or row.gen_company != row.sched_company
                    or review.sent_image_path is None
                    or review.sent_caption is None
                    or row.image_path != review.sent_image_path
                    or row.caption != review.sent_caption):
                review.status = NEEDS_ATTENTION
                review.claimed_at = None
                review.last_error = (
                    "ownership or reviewed content changed after approval;"
                    " not publishing")
                continue
            review.status, review.claimed_at = PUBLISHING, now
            review.attempts += 1
            claims.append(ApprovedReview(
                review.id, review.attempts, review.owner_id,
                review.schedule_id, row.sched_company,
                row.image_path, row.caption))
        await session.commit()
        return claims


async def still_publishing(review_id: UUID, attempt: int) -> bool:
    # preflight read right before the Facebook call: catches a claim
    # already lost. Narrows the stale-worker window without closing it;
    # the bound transitions below protect the row state, but nothing
    # here can stop a remote send already in flight.
    async with async_session_factory() as session:
        return await session.scalar(
            select(R.id).where(R.id == review_id, R.status == PUBLISHING,
                               R.attempts == attempt)) is not None


async def mark_review_published(
    review_id: UUID, attempt: int, facebook_post_id: str
) -> str:
    """Close a successful publish. Returns "published",
    "content_changed" or "stale".

    Locks the review row FOR UPDATE bound to this claim, then the
    schedule and generation rows in that fixed order, so a caption or
    image mutation waits for this transaction and the equality
    re-check is decisive: changed content sends the row to
    needs_attention naming the live post id, and the schedule is not
    marked published. Every write is an UPDATE...RETURNING bound to
    (id, publishing, attempt); a concurrent transition blocks on the
    row lock until commit, then re-evaluates its own predicate.
    """
    async with async_session_factory() as session:
        row = (await session.execute(
            select(R.schedule_id.label("schedule_id"),
                   R.generation_id.label("generation_id"),
                   R.sent_image_path.label("sent_image"),
                   R.sent_caption.label("sent_caption"))
            .where(R.id == review_id, R.status == PUBLISHING,
                   R.attempts == attempt)
            .with_for_update())).first()
        if row is None:
            return "stale"
        schedule_id = row.schedule_id
        generation_id = row.generation_id
        sent_image = row.sent_image
        sent_caption = row.sent_caption
        caption = await session.scalar(
            select(F.caption).where(F.id == schedule_id).with_for_update())
        image_path = await session.scalar(
            select(G.file_path).where(G.id == generation_id)
            .with_for_update())
        if caption != sent_caption or image_path != sent_image:
            matched = await session.scalar(
                update(R)
                .where(R.id == review_id, R.status == PUBLISHING,
                       R.attempts == attempt)
                .values(
                    status=NEEDS_ATTENTION, claimed_at=None,
                    last_error=(
                        "content changed while publishing; facebook post "
                        f"{facebook_post_id} is live and needs a manual look"
                    )[:1000])
                .returning(R.id))
            await session.commit()
            return "content_changed" if matched is not None else "stale"
        matched = await session.scalar(
            update(R)
            .where(R.id == review_id, R.status == PUBLISHING,
                   R.attempts == attempt)
            .values(status=PUBLISHED, claimed_at=None, last_error=None)
            .returning(R.schedule_id))
        if matched is None:
            # unreachable while the row lock above is held; guard anyway
            await session.rollback()
            return "stale"
        await session.execute(
            update(F)
            .where(F.id == schedule_id)
            .values(status="published", facebook_post_id=facebook_post_id))
        await session.commit()
        return "published"


async def mark_publish_failed(review_id: UUID, attempt: int, reason: str) -> bool:
    # publishing -> failed, terminal: Facebook verifiably rejected the post
    return await _transition(review_id, PUBLISHING, FAILED,
                             R.attempts == attempt,
                             claimed_at=None, last_error=reason[:1000])


async def mark_publish_uncertain(review_id: UUID, attempt: int, reason: str) -> bool:
    # publishing -> needs_attention: the request may have reached Facebook
    return await _transition(review_id, PUBLISHING, NEEDS_ATTENTION,
                             R.attempts == attempt,
                             claimed_at=None, last_error=reason[:1000])


REGENERATING = "regenerating"
I = IdeasModel
DI = DesignImageModel


class RegenClaim(NamedTuple):
    review_id: UUID
    attempt: int
    owner_id: UUID
    generation_id: UUID
    prompt: str
    old_path: str


async def claim_rejected_reviews(owner_id: UUID, limit: int = 5) -> list[RegenClaim]:
    """Claim one owner's rejected reviews (rejected -> regenerating).

    Re-validated in the claim transaction; a row that fails goes to
    needs_attention, never to regenerating: the schedule's owner and
    the generation's company owner must be this owner; the review's
    generation must be the schedule's own generation in the schedule's
    company; the generation must be stored with a usable prompt; and no
    other open review may point at the same generation, because swapping
    the image would change that post too. Rows stuck in regenerating
    past STUCK_AFTER go to needs_attention and are never auto-retried.
    The attempt in each claim is its identity; fencing protects
    database transitions only, never an in-flight generation or upload.
    """
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        await session.execute(
            update(R)
            .where(R.status == REGENERATING, R.owner_id == owner_id,
                   R.claimed_at < now - STUCK_AFTER)
            .values(status=NEEDS_ATTENTION,
                    last_error="stuck in regenerating; a new image may have been uploaded"))
        rows = (await session.execute(
            select(R,
                   G.file_path.label("file_path"),
                   G.stored.label("stored"),
                   G.company_id.label("gen_company"),
                   G.prompt_index.label("prompt_index"),
                   I.design_prompts.label("prompts"),
                   F.company_id.label("sched_company"),
                   F.owner_id.label("sched_owner"),
                   D.owner_id.label("co_owner"),
                   F.generation_id.label("sched_gen"))
            .join(F, F.id == R.schedule_id)
            .join(G, G.id == R.generation_id)
            .join(I, I.id == G.ideas_id)
            .join(D, D.id == G.company_id)
            .where(R.status == REJECTED, R.owner_id == owner_id)
            .order_by(R.responded_at).limit(limit)
            .with_for_update(of=R, skip_locked=True))).all()
        claims = []
        for row in rows:
            review = row[0]
            prompts = row.prompts
            prompt_index = row.prompt_index
            prompt = None
            if isinstance(prompts, list) and 0 <= prompt_index < len(prompts):
                prompt = prompts[prompt_index]
            other_open = await session.scalar(
                select(R.id).where(
                    R.generation_id == review.generation_id,
                    R.id != review.id,
                    R.status.notin_([PUBLISHED, FAILED])).limit(1))
            if (row.sched_owner != owner_id or row.co_owner != owner_id
                    or review.generation_id != row.sched_gen
                    or row.gen_company != row.sched_company
                    or not row.stored
                    or not isinstance(prompt, str) or not prompt.strip()
                    or other_open is not None):
                review.status = NEEDS_ATTENTION
                review.claimed_at = None
                review.last_error = (
                    "cannot regenerate: ownership, image or prompt invalid,"
                    " or another review uses this image")
                continue
            review.status, review.claimed_at = REGENERATING, now
            review.attempts += 1
            claims.append(RegenClaim(
                review.id, review.attempts, review.owner_id,
                review.generation_id, prompt, row.file_path))
        await session.commit()
        return claims


async def still_regenerating(review_id: UUID, attempt: int) -> bool:
    # preflight read before the paid generation call: narrows the
    # stale-worker window, never closes it
    async with async_session_factory() as session:
        return await session.scalar(
            select(R.id).where(R.id == review_id, R.status == REGENERATING,
                               R.attempts == attempt)) is not None


async def finish_regeneration(
    review_id: UUID, attempt: int, old_path: str, new_path: str, new_url: str
) -> str:
    """Swap in the regenerated image. Returns "done", "changed" or "stale".

    Locks the review row FOR UPDATE bound to this claim, then the
    generation row (same order as mark_review_published). If the
    generation's path is no longer the claimed old path, or it is not
    stored, the row goes to needs_attention and "changed" is returned.
    On "done" the generation path and the design image URL point at the
    new file and the review is pending again, with its message id and
    reviewed content cleared so the next send is a fresh review that
    needs a new approval. The caller deletes the old file only after
    "done", and the new file otherwise.
    """
    async with async_session_factory() as session:
        gen_id = await session.scalar(
            select(R.generation_id)
            .where(R.id == review_id, R.status == REGENERATING,
                   R.attempts == attempt)
            .with_for_update())
        if gen_id is None:
            return "stale"
        row = (await session.execute(
            select(G.file_path.label("file_path"),
                   G.stored.label("stored"),
                   G.ideas_id.label("ideas_id"),
                   G.prompt_index.label("prompt_index"))
            .where(G.id == gen_id).with_for_update())).first()
        if row is None or row.file_path != old_path or not row.stored:
            await session.execute(
                update(R)
                .where(R.id == review_id, R.status == REGENERATING,
                       R.attempts == attempt)
                .values(status=NEEDS_ATTENTION, claimed_at=None,
                        last_error="image changed while regenerating; not swapped"))
            await session.commit()
            return "changed"
        ideas_id, prompt_index = row.ideas_id, row.prompt_index
        await session.execute(
            update(G).where(G.id == gen_id).values(file_path=new_path))
        await session.execute(
            update(DI)
            .where(DI.ideas_id == ideas_id, DI.prompt_index == prompt_index)
            .values(file_path=new_url))
        matched = await session.scalar(
            update(R)
            .where(R.id == review_id, R.status == REGENERATING,
                   R.attempts == attempt)
            .values(status=PENDING, claimed_at=None, last_error=None,
                    telegram_message_id=None, sent_image_path=None,
                    sent_caption=None)
            .returning(R.id))
        if matched is None:
            # unreachable while the row lock above is held; guard anyway
            await session.rollback()
            return "stale"
        await session.commit()
        return "done"


async def mark_regeneration_failed(review_id: UUID, attempt: int, reason: str) -> bool:
    # regenerating -> needs_attention: generation or upload failed; never
    # auto-retried because every try is a paid image generation
    return await _transition(review_id, REGENERATING, NEEDS_ATTENTION,
                             R.attempts == attempt,
                             claimed_at=None, last_error=reason[:1000])