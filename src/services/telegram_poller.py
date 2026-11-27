"""Telegram callback poller for the review flow (not wired yet).

Long-polls getUpdates, feeds review-button taps to
telegram_callbacks.handle_review_callback, and answers each tap with
answerCallbackQuery. Configuration is validated before the first fetch:
a missing or invalid TELEGRAM_CHAT_ID / TELEGRAM_REVIEWER_USER_ID /
TELEGRAM_REVIEW_OWNER_ID raises before any update is consumed.

Offset discipline: the offset advances past a batch only after every
tap in it was handled; an empty batch preserves the incoming offset.
A poison update (no usable identity) is skipped and logged, never
retried forever. A tap whose handler crashes is never silently dropped:
the user gets a best-effort "tap again" answer, only earlier updates
are acknowledged, and the batch redelivers from that tap. The handler
is idempotent, so earlier taps in a redelivered batch are refused with
their current state instead of transitioning twice. The run loop waits
between such retries with capped exponential backoff (_handler_backoff).

Error policy: TelegramRejected (bad token, blocked bot) is a
configuration problem and stops the loop loudly instead of spinning.
TelegramUncertain / TelegramUnreachable wait POLL_SECONDS and retry:
for getUpdates an uncertain retry is safe because nothing was consumed.
Bot errors are logged by their fixed classification only, without
exc_info (the client pins token-carrying URLs out of its messages, and
callers must keep tracebacks out of logs). A failure while answering a
tap is logged and never blocks the loop - the state transition already
happened, the toast is cosmetic.
"""

import asyncio
import logging
import math
from typing import NamedTuple

from src.services import telegram_callbacks as tc
from src.services.telegram_bot import (
    TelegramBot,
    TelegramRejected,
    TelegramUncertain,
    TelegramUnreachable,
)

logger = logging.getLogger(__name__)

LONG_POLL_SECONDS = 25
POLL_SECONDS = 5
MAX_HANDLER_BACKOFF = 60
RETRY_ANSWER = "حصلت مشكلة مؤقتة، دوس تاني."


class CallbackTap(NamedTuple):
    update_id: int
    query_id: str
    data: str
    from_user_id: int
    chat_id: str
    message_id: str


class _HandlerFailed(Exception):
    """A valid tap hit an internal error; carries the offset to resume from."""

    def __init__(self, resume_offset: int):
        super().__init__("handler failed; the batch will be redelivered")
        self.resume_offset = resume_offset


def _handler_backoff(failures: int) -> float:
    """Capped exponential wait between handler-failure retries; the
    exponent itself is capped first, so a long failure streak never
    builds a giant number that the cap then discards."""
    exp_cap = max(0, math.ceil(math.log2(MAX_HANDLER_BACKOFF / POLL_SECONDS)))
    return float(min(POLL_SECONDS * (2 ** min(failures - 1, exp_cap)),
                     MAX_HANDLER_BACKOFF))

def _extract_taps(updates: list) -> tuple[list[CallbackTap], int | None]:
    """Parseable taps plus the highest update id seen (to acknowledge).

    A callback missing any identity field (from, chat, message, data) is
    skipped whole - a partial identity is never guessed.
    """
    taps: list[CallbackTap] = []
    max_id = None
    for update in updates:
        if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
            continue
        uid = update["update_id"]
        max_id = uid if max_id is None else max(max_id, uid)
        query = update.get("callback_query")
        if not isinstance(query, dict):
            continue  # plain message or other update kind: just acknowledge
        try:
            taps.append(CallbackTap(
                update_id=uid,
                query_id=str(query["id"]),
                data=str(query["data"]),
                from_user_id=int(query["from"]["id"]),
                chat_id=str(query["message"]["chat"]["id"]),
                message_id=str(query["message"]["message_id"]),
            ))
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping unparseable callback_query in update %s", uid)
    return taps, max_id


async def _handle_tap(bot: TelegramBot, tap: CallbackTap) -> bool:
    """Handle one tap; False means the handler crashed and the tap must retry."""
    try:
        outcome = await tc.handle_review_callback(
            tap.data, tap.from_user_id, tap.chat_id, tap.message_id)
    except Exception:
        logger.exception("Review callback handler failed; the tap will be retried")
        try:
            await bot.answer_callback_query(tap.query_id, RETRY_ANSWER)
        except Exception as exc:
            logger.error("Retry-needed answer could not be delivered: %s", exc)
        return False
    try:
        await bot.answer_callback_query(tap.query_id, outcome.answer)
    except Exception as exc:
        # the transition already happened; the toast is cosmetic
        logger.error("answerCallbackQuery failed: %s", exc)
    return True

async def _poll_once(bot: TelegramBot, offset: int | None) -> int | None:
    """Fetch one batch, handle and answer its taps, return the next offset.

    Stops at the first tap whose handler crashed and raises
    _HandlerFailed carrying that tap's update id: only earlier updates
    are acknowledged, so the failed tap and everything after it
    redelivers. An empty batch preserves the incoming offset.
    """
    updates = await bot.get_updates(offset, LONG_POLL_SECONDS)
    taps, max_id = _extract_taps(updates)
    for tap in taps:
        if not await _handle_tap(bot, tap):
            raise _HandlerFailed(resume_offset=tap.update_id)
    return offset if max_id is None else max_id + 1


async def _poll_cycle(bot: TelegramBot, offset: int | None) -> int | None:
    """One fetch cycle with the transport error policy.

    TelegramRejected propagates (stop loudly); uncertain/unreachable
    waits and keeps the offset; a handler failure propagates as
    _HandlerFailed for the run loop's backoff.
    """
    try:
        return await _poll_once(bot, offset)
    except TelegramRejected:
        raise  # configuration problem (bad token, blocked bot): stop loudly
    except (TelegramUncertain, TelegramUnreachable) as exc:
        logger.error("getUpdates failed (%s); retrying shortly", exc)
        await asyncio.sleep(POLL_SECONDS)
        return offset


async def run_callback_poller(bot: TelegramBot) -> None:
    """Poll forever; startup wiring comes in a later step."""
    tc._callback_config()  # fail closed before the first fetch
    offset = None
    failures = 0
    while True:
        try:
            offset = await _poll_cycle(bot, offset)
            failures = 0
        except _HandlerFailed as exc:
            failures += 1
            offset = exc.resume_offset
            await asyncio.sleep(_handler_backoff(failures))