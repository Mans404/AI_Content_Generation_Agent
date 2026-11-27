"""Telegram callback handling for the review flow (not wired yet).

This module turns one tapped approve/reject button into a state
transition. It makes no Telegram calls: the future webhook or poller
extracts the fields from the actual callback_query object (data,
from.id, message.chat.id, message.message_id), calls
handle_review_callback, and sends the returned answer back with
answerCallbackQuery.

Identity gates, every one fails closed:
- the callback's chat id must equal the configured TELEGRAM_CHAT_ID;
- the callback's from-user id must equal TELEGRAM_REVIEWER_USER_ID - the
  actual Telegram sender identity from the update, never a
  caller-provided UUID;
- the review row itself is read and transitioned only under the
  configured owner (TELEGRAM_REVIEW_OWNER_ID), and mark_approved /
  mark_rejected additionally bind the row's current telegram_message_id,
  so a stale button from an older message can never move a re-sent
  review.

Partial content is never approved: a tap while the row is still sending
(text possibly still on its way) is deferred - the row is re-read for
up to RETRY_SECONDS, and if it has not settled the user is told to tap
again. Only a row that reached awaiting_approval can transition.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from src.database.companies import async_session_factory
from src.models.companies import TelegramPostReviewModel
from src.services import telegram_reviews as tr

logger = logging.getLogger(__name__)

R = TelegramPostReviewModel
RETRY_SECONDS = 3.0
RETRY_INTERVAL = 0.5


@dataclass
class CallbackOutcome:
    answer: str
    acted: bool  # True only when a state transition actually happened


def _callback_config() -> tuple[str, int, UUID]:
    """Chat, reviewer user id, and owner; fails closed unless all are set."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    reviewer = os.getenv("TELEGRAM_REVIEWER_USER_ID")
    owner_raw = os.getenv("TELEGRAM_REVIEW_OWNER_ID")
    if not chat_id or not reviewer or not owner_raw:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID, TELEGRAM_REVIEWER_USER_ID and"
            " TELEGRAM_REVIEW_OWNER_ID must all be configured.")
    try:
        return chat_id, int(reviewer), UUID(owner_raw)
    except ValueError:
        raise RuntimeError(
            "TELEGRAM_REVIEWER_USER_ID must be an integer and"
            " TELEGRAM_REVIEW_OWNER_ID a valid UUID.") from None

async def _read_review(review_id: UUID, owner_id: UUID) -> TelegramPostReviewModel | None:
    # read under the configured owner only: another owner's row is invisible
    async with async_session_factory() as session:
        return await session.scalar(
            select(R).where(R.id == review_id, R.owner_id == owner_id))


async def handle_review_callback(
    callback_data: str, from_user_id: int, chat_id: str, message_id: str
) -> CallbackOutcome:
    """Process one tapped review button; the caller answers Telegram."""
    expected_chat, reviewer_id, owner_id = _callback_config()
    if str(chat_id) != str(expected_chat) or from_user_id != reviewer_id:
        logger.warning("Callback from unexpected chat or user refused")
        return CallbackOutcome("الزر ده مش ليك.", False)
    try:
        action, raw_id = callback_data.split(":", 1)
        review_id = UUID(raw_id)
    except ValueError:
        return CallbackOutcome("زر غير معروف.", False)
    if action not in ("approve", "reject"):
        return CallbackOutcome("زر غير معروف.", False)
    row = await _read_review(review_id, owner_id)
    # defer while the sender may still be delivering the full text
    waited = 0.0
    while row is not None and row.status == tr.SENDING and waited < RETRY_SECONDS:
        await asyncio.sleep(RETRY_INTERVAL)
        waited += RETRY_INTERVAL
        row = await _read_review(review_id, owner_id)
    if row is None or row.telegram_message_id != str(message_id):
        # unknown row, or a stale button from an older message
        return CallbackOutcome("رسالة قديمة، راجع أحدث رسالة.", False)
    if row.status == tr.SENDING:
        return CallbackOutcome("لسه المحتوى بيتجهز، دوس تاني بعد ثواني.", False)
    if action == "approve":
        done = await tr.mark_approved(review_id, owner_id, str(message_id))
    else:
        done = await tr.mark_rejected(review_id, owner_id, str(message_id))
    if done:
        return CallbackOutcome(
            "تمت الموافقة." if action == "approve" else "تم الرفض.", True)
    return CallbackOutcome(f"اتعاملت قبل كده. الحالة: {row.status}.", False)