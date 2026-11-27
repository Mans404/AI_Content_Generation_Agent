"""Publish worker: posts approved reviews to Facebook for one owner.

The loop starts only when TELEGRAM_REVIEW_OWNER_ID (a valid UUID) is
configured and claims only that owner's approved reviews. Per claim: a
still_publishing preflight narrows the stale-worker window (the
attempt-bound transitions are what protect the row); the published
image and caption come from the claim snapshot, which the claim
validated against the content the reviewer was sent - the schedule and
generation rows are never re-read here, so the post always carries
exactly the approved content.

Outcomes: a returned post id closes the publish through
mark_review_published, which re-checks the reviewed content in its
commit transaction (a mid-flight change surfaces as needs_attention
naming the live post). A PublishRejected marks the review failed,
terminal, with no retry. A PublishUncertain sends the row to
needs_attention: the post may exist on Facebook, so no automatic path
ever republishes - a duplicate is still possible through manual
reconciliation after an uncertain outcome, and the preflight cannot
stop a remote call already in flight.

Nothing calls this yet; wiring into app startup comes in a later step,
together with the Facebook page configuration.
"""

import asyncio
import logging
import os
from typing import Protocol
from uuid import UUID

from src.services import telegram_reviews as tr
from src.services.facebook_review_client import (
    PublishRejected,
    PublishUncertain,
)
from src.services.storage import DESIGN_IMAGES_BUCKET, supabase_storage

logger = logging.getLogger(__name__)

POLL_SECONDS = 30


class ReviewPublisher(Protocol):
    async def publish_photo(self, image_url: str, caption: str) -> str:
        """Publish one photo post; return its Facebook post id."""


async def _publish_one(
    publisher: ReviewPublisher, owner_id: UUID, claim: tr.ApprovedReview
) -> None:
    rid, attempt = claim.review_id, claim.attempt
    if claim.owner_id != owner_id:
        # fail closed: a claim for any other owner is never published
        logger.error(
            "Review %s claimed for an unexpected owner; not publishing", rid)
        return
    if not await tr.still_publishing(rid, attempt):
        return  # claim already lost: skip the post (a loss after this read
        # is still possible; the bound transitions protect the row)
    image_url = supabase_storage.public_url(
        DESIGN_IMAGES_BUCKET, claim.image_path)
    try:
        post_id = await publisher.publish_photo(image_url, claim.caption)
    except PublishRejected as exc:
        await tr.mark_publish_failed(rid, attempt, str(exc))
        return
    except PublishUncertain as exc:
        await tr.mark_publish_uncertain(rid, attempt, str(exc))
        return
    result = await tr.mark_review_published(rid, attempt, post_id)
    if result == "content_changed":
        logger.warning(
            "Review %s content changed while publishing; facebook post %s"
            " is live and needs a manual look", rid, post_id)
    elif result == "stale":
        logger.warning(
            "Review %s moved on while publishing; facebook post %s may be"
            " live and needs a manual look", rid, post_id)


def _owner_config() -> UUID:
    raw = os.getenv("TELEGRAM_REVIEW_OWNER_ID")
    if not raw:
        raise RuntimeError("TELEGRAM_REVIEW_OWNER_ID must be configured.")
    try:
        return UUID(raw)
    except ValueError:
        raise RuntimeError(
            "TELEGRAM_REVIEW_OWNER_ID must be a valid UUID.") from None


async def run_review_publisher_loop(publisher: ReviewPublisher) -> None:
    owner_id = _owner_config()
    while True:
        try:
            approved = await tr.claim_approved_reviews(owner_id)
            results = await asyncio.gather(
                *(_publish_one(publisher, owner_id, claim)
                  for claim in approved),
                return_exceptions=True)
            for claim, result in zip(approved, results):
                if isinstance(result, Exception):
                    logger.error(
                        "Publish for review %s failed unexpectedly: %r",
                        claim.review_id, result)
        except Exception:
            logger.exception("Review publisher iteration failed")
        await asyncio.sleep(POLL_SECONDS)