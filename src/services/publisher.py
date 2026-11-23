import asyncio, logging
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID
from sqlalchemy import select, update

from src.database.companies import async_session_factory
from src.models.companies import ScheduledPostModel as P, ScheduledPostStatus as S

logger = logging.getLogger(__name__)
POLL_SECONDS = 30
MAX_ATTEMPTS = 3
STUCK_AFTER = timedelta(minutes=10)


class SocialPublisher(Protocol):
    async def publish(self, image_url: str, caption: str) -> str:
        """Post it and return the platform's post id."""


async def _claim_due(limit: int = 10):
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        # Recover rows left in 'publishing' by a crashed worker.
        # (Small risk of a duplicate post if the crash happened after the platform accepted it.)
        await session.execute(
            update(P)
            .where(P.status == S.PUBLISHING.value, P.claimed_at < now - STUCK_AFTER)
            .values(status=S.SCHEDULED.value)
        )
        rows = (await session.scalars(
            select(P)
            .where(P.status == S.SCHEDULED.value, P.scheduled_at <= now)
            .order_by(P.scheduled_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )).all()
        for r in rows:
            r.status, r.claimed_at, r.attempts = S.PUBLISHING.value, now, r.attempts + 1
        await session.commit()
        return [(r.id, r.image_url, r.caption, r.attempts) for r in rows]


async def _publish_one(publisher: SocialPublisher, post_id, image_url, caption, attempts):
    try:
        external_id = await publisher.publish(image_url, caption)
    except Exception as exc:
        logger.exception("Publishing %s failed (attempt %s)", post_id, attempts)
        await _mark_failed(post_id, attempts, exc)
        return

    await _mark_published(post_id, external_id)


async def _mark_failed(post_id: UUID, attempts: int, exc: Exception) -> None:
    async with async_session_factory() as session:
        post = await session.get(P, post_id)
        if post is None:
            logger.warning("Scheduled post %s disappeared before the failure was recorded", post_id)
            return
        post.last_error = str(exc)[:1000]
        if attempts >= MAX_ATTEMPTS:
            post.status = S.FAILED.value
        else:
            post.status = S.SCHEDULED.value
            post.scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=5 * attempts)
        await session.commit()


async def _mark_published(post_id: UUID, external_id: str) -> None:
    for attempt in range(3):
        try:
            async with async_session_factory() as session:
                post = await session.get(P, post_id)
                if post is None:
                    logger.error(
                        "Post %s was published (external id %s) but its row no longer exists",
                        post_id, external_id,
                    )
                    return
                post.status = S.PUBLISHED.value
                post.published_at = datetime.now(timezone.utc)
                post.external_post_id = external_id
                post.last_error = None
                await session.commit()
                return
        except Exception:
            logger.exception("Could not record published post %s (try %s)", post_id, attempt + 1)
            await asyncio.sleep(2 ** attempt)
    logger.critical(
        "Post %s is live (external id %s) but could not be marked published; it may be re-posted",
        post_id, external_id,
    )


async def run_publisher_loop(publisher: SocialPublisher) -> None:
    while True:
        try:
            due = await _claim_due()
            await asyncio.gather(*(_publish_one(publisher, *d) for d in due))
        except Exception:
            logger.exception("Publisher loop iteration failed")
        await asyncio.sleep(POLL_SECONDS)