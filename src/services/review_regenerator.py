"""Regenerate worker: replaces the image of rejected reviews for one owner.

The loop starts only when TELEGRAM_REVIEW_OWNER_ID (a valid UUID) is
configured and claims only that owner's rejected reviews. Per claim: one
paid image generation from the claim's prompt snapshot, an upload to a
brand new storage path (the old file is never overwritten), then one
commit through finish_regeneration that swaps the generation path and
the design image URL and returns the review to pending. The next send
is a fresh review: it needs a new approval, and nothing here ever
approves or publishes anything.

Cap: at most MAX_REGENERATIONS per image. The count lives in the image
path itself (<generation id>.<ext> is 0, each regeneration writes
<generation id>-r<N>-<random>.<ext>), so it needs no schema change and
survives restarts; a path in any other shape fails closed. Over the cap
the review goes to needs_attention before any generation, so nothing is
spent.

Failures: any generation, upload or URL error marks the review
needs_attention with a fixed reason and is never retried automatically,
because every try is a paid generation. An unknown commit outcome also
goes to needs_attention and keeps the new file, since the commit may
have succeeded and referenced it. A "changed" or "stale" result deletes
the new file; "done" deletes the old one. Deletes are best effort.
Fencing protects database transitions only, never an in-flight
generation or upload.

Nothing calls this yet; wiring into app startup comes in a later step.
"""

import asyncio
import logging
import os
import re
from typing import Protocol
from uuid import UUID, uuid4

from src.agents.design_image_agent import GeneratedImage
from src.services import telegram_reviews as tr
from src.services.storage import DESIGN_IMAGES_BUCKET, supabase_storage

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
MAX_REGENERATIONS = 3
CONTENT_TYPES = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
_PATH = re.compile(r"(?:-r(\d+)-[0-9a-f]{32})?\.(?:jpeg|png|webp)")


class ImageGenerator(Protocol):
    async def generate(self, design_prompt: str) -> GeneratedImage:
        """Generate one image from a design prompt."""


async def _safe_delete(path: str) -> None:
    try:
        await supabase_storage.delete(DESIGN_IMAGES_BUCKET, path)
    except Exception:
        logger.warning("Could not remove design image %s", path)


def regeneration_count(generation_id: UUID, path: str) -> int | None:
    """How many times this image was regenerated; None for an unknown shape."""
    prefix = str(generation_id)
    if not path.startswith(prefix):
        return None
    match = _PATH.fullmatch(path[len(prefix):])
    if match is None:
        return None
    return int(match.group(1)) if match.group(1) else 0

async def _regenerate_one(
    generator: ImageGenerator, owner_id: UUID, claim: tr.RegenClaim
) -> None:
    rid, attempt = claim.review_id, claim.attempt
    if claim.owner_id != owner_id:
        # fail closed: a claim for any other owner is never regenerated
        logger.error(
            "Review %s claimed for an unexpected owner; not regenerating", rid)
        return
    if not await tr.still_regenerating(rid, attempt):
        return
    count = regeneration_count(claim.generation_id, claim.old_path)
    if count is None or count >= MAX_REGENERATIONS:
        logger.warning("Review %s is not eligible for regeneration", rid)
        await tr.mark_regeneration_failed(
            rid, attempt, "regeneration limit reached or image path unknown")
        return
    new_path = ""
    try:
        generated = await generator.generate(claim.prompt)
        extension = generated.extension
        if extension not in CONTENT_TYPES or not generated.data:
            raise ValueError("unusable generated image")
        new_path = (f"{claim.generation_id}-r{count + 1}-"
                    f"{uuid4().hex}.{extension}")
        await supabase_storage.upload(
            DESIGN_IMAGES_BUCKET, new_path, generated.data,
            CONTENT_TYPES[extension])
        new_url = supabase_storage.public_url(DESIGN_IMAGES_BUCKET, new_path)
    except Exception as exc:
        logger.error("Regeneration for review %s failed: %s",
                     rid, type(exc).__name__)
        await tr.mark_regeneration_failed(
            rid, attempt, "image generation or upload failed")
        if new_path:
            await _safe_delete(new_path)
        return
    try:
        result = await tr.finish_regeneration(
            rid, attempt, claim.old_path, new_path, new_url)
    except Exception as exc:
        # the commit may have succeeded and referenced the new file, so
        # it is kept; a still-regenerating row goes to needs_attention
        logger.error("Regeneration commit for review %s is unknown: %s",
                     rid, type(exc).__name__)
        await tr.mark_regeneration_failed(
            rid, attempt, "regeneration commit outcome unknown")
        return
    if result == "done":
        await _safe_delete(claim.old_path)
    else:
        logger.warning(
            "Review %s regeneration was %s; new image discarded", rid, result)
        await _safe_delete(new_path)


def _owner_config() -> UUID:
    raw = os.getenv("TELEGRAM_REVIEW_OWNER_ID")
    if not raw:
        raise RuntimeError("TELEGRAM_REVIEW_OWNER_ID must be configured.")
    try:
        return UUID(raw)
    except ValueError:
        raise RuntimeError(
            "TELEGRAM_REVIEW_OWNER_ID must be a valid UUID.") from None


async def run_review_regenerator_loop(generator: ImageGenerator) -> None:
    owner_id = _owner_config()
    while True:
        try:
            claims = await tr.claim_rejected_reviews(owner_id)
            results = await asyncio.gather(
                *(_regenerate_one(generator, owner_id, claim)
                  for claim in claims),
                return_exceptions=True)
            for claim, result in zip(claims, results):
                if isinstance(result, Exception):
                    logger.error(
                        "Regeneration for review %s failed unexpectedly: %s",
                        claim.review_id, type(result).__name__)
        except Exception as exc:
            logger.error("Review regenerator iteration failed: %s",
                         type(exc).__name__)
        await asyncio.sleep(POLL_SECONDS)