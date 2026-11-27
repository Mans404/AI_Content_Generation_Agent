"""Minimal Telegram Bot API client for the review flow (send only).

Reads the bot token from TELEGRAM_BOT_TOKEN at construction, never at
import, so the module loads with no configuration present.

The token is part of every request URL, so it must never leak through
errors or logs: every raised exception carries only a fixed
classification (the method, an HTTP status or an httpx error class
name), the original exception chain is suppressed, and Telegram's raw
response text is never included. Construction also pins the httpx and
httpcore loggers to WARNING, because their INFO/DEBUG request lines
contain the full URL with the token. Callers must log these errors
without exc_info.
"""

import logging
import os

import httpx


class TelegramUnreachable(Exception):
    """The request never reached Telegram (connect error/timeout). Safe to retry."""


class TelegramRejected(Exception):
    """Telegram answered 4xx (bad token/chat, blocked bot). Permanent: fix config."""


class TelegramUncertain(Exception):
    """The request may or may not have arrived (timeout after send, 5xx,
    unreadable response, or an ok response without a message id). Never
    auto-retry: a duplicate message is possible."""


REVIEW_PHOTO_CAPTION = "منشور مجدول بانتظار المراجعة. النص الكامل في الرسائل التالية."


class TelegramBot:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN must be configured.")
        self.base = f"https://api.telegram.org/bot{self.token}"
        # httpx/httpcore log full request URLs (with the token) at
        # INFO/DEBUG: pin them to WARNING so the token never hits logs.
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)

    async def _request(self, method: str, payload: dict, timeout: float = 30.0):
        """POST one Bot API call and return the raw result.

        Errors are classified (unreachable / rejected / uncertain) and
        carry only the method, an HTTP status or an httpx error class
        name - never the URL, which contains the token.
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{self.base}/{method}", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise TelegramUnreachable(
                f"{method}: connect failed ({type(exc).__name__})") from None
        except httpx.HTTPError as exc:
            raise TelegramUncertain(
                f"{method}: transport error ({type(exc).__name__})") from None
        if response.status_code >= 500:
            raise TelegramUncertain(f"{method}: telegram HTTP {response.status_code}")
        if response.status_code >= 400:
            raise TelegramRejected(
                f"{method}: telegram rejected HTTP {response.status_code}")
        if response.status_code != 200:
            raise TelegramUncertain(f"{method}: unexpected HTTP {response.status_code}")
        try:
            data = response.json()
        except Exception:
            raise TelegramUncertain(f"{method}: unreadable ok response") from None
        if not (isinstance(data, dict) and data.get("ok")) or "result" not in data:
            raise TelegramUncertain(f"{method}: ok response without a result")
        return data["result"]

    async def _post(self, method: str, payload: dict) -> dict:
        result = await self._request(method, payload)
        if not isinstance(result, dict) or not isinstance(result.get("message_id"), int):
            # Telegram said ok but we cannot identify the message: it may be
            # delivered, so this is uncertain, never auto-retried.
            raise TelegramUncertain(f"{method}: ok response without a message id")
        return result

    async def send_photo_for_review(
        self, chat_id: str, image_url: str, review_id
    ) -> str:
        """Send the image with a short fixed caption and approve/reject
        buttons; return the Telegram message id. The full post text goes
        in follow-up text messages, so no user text is truncated here."""
        payload = {
            "chat_id": chat_id,
            "photo": image_url,
            "caption": f"{REVIEW_PHOTO_CAPTION} (مراجعة {str(review_id)[:8]})",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "موافقة", "callback_data": f"approve:{review_id}"},
                    {"text": "رفض", "callback_data": f"reject:{review_id}"},
                ]]
            },
        }
        result = await self._post("sendPhoto", payload)
        return str(result["message_id"])

    async def send_text(self, chat_id: str, text: str) -> str:
        """Send one plain text message (the caller chunks to Telegram's limit)."""
        result = await self._post("sendMessage", {"chat_id": chat_id, "text": text})
        return str(result["message_id"])

    async def get_updates(self, offset: int | None, timeout: int) -> list:
        """Long-poll updates after offset; returns the raw update list.

        An uncertain outcome here is safe to retry: nothing is consumed
        until the caller advances the offset past processed updates.
        """
        payload: dict = {"timeout": timeout, "allowed_updates": ["callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        result = await self._request("getUpdates", payload, timeout=timeout + 10)
        if not isinstance(result, list):
            raise TelegramUncertain("getUpdates: result is not a list")
        return result

    async def answer_callback_query(self, callback_query_id: str, text: str) -> None:
        """Answer one tapped button; delivery of the toast is best-effort."""
        await self._request("answerCallbackQuery", {
            "callback_query_id": callback_query_id, "text": text})