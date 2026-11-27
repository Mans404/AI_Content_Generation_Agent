"""Due-time sender: delivers claimed reviews to Telegram for approval.

One authorized destination: the loop starts only when TELEGRAM_CHAT_ID
and TELEGRAM_REVIEW_OWNER_ID (a valid UUID) are both configured, claims
only that owner's reviews, and _send_one re-validates each claim's
owner before sending. The UUID is local routing configuration, not
proof of anyone's Telegram identity.

Per claim: a still_claimed preflight narrows the stale-worker window
(the attempt-bound transitions are what protect the row); the image
comes from the claim's generation snapshot; the photo goes out with
approve/reject buttons and a short fixed caption; the full text follows
in exact substrings under Telegram's UTF-16 limit; and the photo's
message id is stored before the text, so every failure after that point
keeps it on the row. A crash between Telegram accepting the photo and
that record committing leaves an unrecorded message; the stuck-sending
sweep then surfaces the row for a human to reconcile.

Outcomes: a photo that never reached Telegram is requeued up to
MAX_SEND_ATTEMPTS, then needs_attention. Any failure after Telegram was
reached goes to needs_attention with the photo's id when there is one;
no automatic path resends, so this worker has no automatic duplication
path - a duplicate is still possible through manual re-sending after an
uncertain outcome or an unrecorded delivery. The row reaches
awaiting_approval only after the full text is delivered, and the
callback step must refuse or defer taps while the row is sending, so
partial content can never be approved.

Nothing calls this yet; wiring into app startup comes in a later step,
together with the bot token and chat id configuration.
"""

import asyncio
import logging
import os
from typing import Protocol
from uuid import UUID

from src.services import telegram_reviews as tr
from src.services.storage import DESIGN_IMAGES_BUCKET, supabase_storage
from src.services.telegram_bot import (
    TelegramRejected,
    TelegramUncertain,
    TelegramUnreachable,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
MAX_SEND_ATTEMPTS = 5
TEXT_LIMIT = 4000  # UTF-16 code units per text message (Telegram allows 4096)


class ReviewSender(Protocol):
    async def send_photo_for_review(
        self, chat_id: str, image_url: str, review_id: UUID
    ) -> str:
        """Send the review photo with buttons; return its message id."""

    async def send_text(self, chat_id: str, text: str) -> str:
        """Send one plain text message; return its message id."""

def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _chunks(text: str) -> list[str]:
    """Split into exact substrings, each under TEXT_LIMIT UTF-16 units.

    ''.join(chunks) == text always: separators stay at the end of the
    preceding chunk and are never stripped. Prefers splitting after a
    newline, then after a space, inside the window; otherwise hard-
    splits at the largest prefix that fits.
    """
    chunks: list[str] = []
    rest = text
    while rest:
        if _utf16_len(rest) <= TEXT_LIMIT:
            chunks.append(rest)
            break
        lo, hi = 0, min(len(rest), TEXT_LIMIT)
        while lo < hi:  # largest prefix (code points) within the UTF-16 limit
            mid = (lo + hi + 1) // 2
            if _utf16_len(rest[:mid]) <= TEXT_LIMIT:
                lo = mid
            else:
                hi = mid - 1
        window = rest[:lo]
        sep = window.rfind("\n")
        if sep < lo // 2:
            sep = window.rfind(" ")
        cut = sep + 1 if sep >= lo // 2 else lo
        chunks.append(rest[:cut])
        rest = rest[cut:]
    return chunks


async def _send_one(
    sender: ReviewSender, chat_id: str, owner_id: UUID, claim: tr.ClaimedReview
) -> None:
    rid, attempt = claim.review_id, claim.attempt
    if claim.owner_id != owner_id:
        # fail closed: a claim for any other owner never reaches the chat
        logger.error("Review %s claimed for an unexpected owner; not sending", rid)
        return
    if not await tr.still_claimed(rid, attempt):
        return  # claim already lost: skip the send (a loss after this read
        # is still possible; the bound transitions protect the row)
    image_url = supabase_storage.public_url(DESIGN_IMAGES_BUCKET, claim.image_path)
    try:
        photo_message_id = await sender.send_photo_for_review(chat_id, image_url, rid)
    except TelegramUnreachable:
        if attempt < MAX_SEND_ATTEMPTS:
            await tr.requeue_sending(rid, attempt)
        else:
            await tr.mark_needs_attention(
                rid, attempt, f"telegram unreachable after {attempt} attempts")
        return
    except (TelegramRejected, TelegramUncertain) as exc:
        await tr.mark_needs_attention(rid, attempt, f"photo send: {exc}")
        return
    if not await tr.record_photo_progress(rid, attempt, photo_message_id, claim.image_path, claim.caption):
        logger.warning(
            "Review %s moved on after photo delivery; telegram message %s"
            " needs a manual look", rid, photo_message_id)
        return
    try:
        if claim.caption.strip():
            for part in _chunks(claim.caption):
                await sender.send_text(chat_id, part)
    except (TelegramUnreachable, TelegramRejected, TelegramUncertain) as exc:
        # The photo is already on Telegram; any retry would duplicate it.
        await tr.mark_needs_attention(
            rid, attempt,
            f"photo delivered as telegram message {photo_message_id};"
            f" text send failed: {exc}")
        return
    if not await tr.mark_awaiting_approval(rid, attempt, photo_message_id):
        logger.warning(
            "Review %s moved on after full delivery; telegram message %s"
            " needs a manual look", rid, photo_message_id)

def _destination_config() -> tuple[str, UUID]:
    """The one authorized destination; fails closed unless fully configured."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    owner_raw = os.getenv("TELEGRAM_REVIEW_OWNER_ID")
    if not chat_id or not owner_raw:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID and TELEGRAM_REVIEW_OWNER_ID must both be configured.")
    try:
        return chat_id, UUID(owner_raw)
    except ValueError:
        raise RuntimeError(
            "TELEGRAM_REVIEW_OWNER_ID must be a valid UUID.") from None


async def run_review_sender_loop(sender: ReviewSender) -> None:
    chat_id, owner_id = _destination_config()
    while True:
        try:
            due = await tr.claim_due_reviews(owner_id)
            results = await asyncio.gather(
                *(_send_one(sender, chat_id, owner_id, claim) for claim in due),
                return_exceptions=True)
            for claim, result in zip(due, results):
                if isinstance(result, Exception):
                    logger.error(
                        "Send for review %s failed unexpectedly: %r",
                        claim.review_id, result)
        except Exception:
            logger.exception("Review sender iteration failed")
        await asyncio.sleep(POLL_SECONDS)