"""Minimal Facebook Graph client for publishing reviewed posts only.

Reads FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN at construction,
never at import, so the module loads with no configuration present.
The page access token goes in the request body, never the URL, and
every raised exception carries only a fixed classification (an HTTP
status, a Graph error code number, or an httpx error class name) -
never Graph's raw response text, which can echo request data.
Construction pins the httpx and httpcore loggers to WARNING. Callers
must log these errors without exc_info.

Error taxonomy: only a 4xx with a parseable Graph error body is a
verified rejection (PublishRejected): the review may be marked failed
and must not be retried. Everything else - a transport error, 5xx, an
unreadable or unexpected response, a 4xx without a parseable Graph
error, a 2xx without a usable post id - is PublishUncertain: the
request may have reached Facebook, so the post may exist; never
auto-retry.
"""

import logging
import os

import httpx


class PublishRejected(Exception):
    """Facebook verifiably rejected the post: 4xx with a parseable
    Graph error body. Terminal, no retry."""


class PublishUncertain(Exception):
    """The request may or may not have been accepted: transport error,
    5xx, unreadable or unexpected response, or a 2xx without a usable
    post id. Never auto-retry: a duplicate post is possible."""


DEFAULT_GRAPH_VERSION = "v22.0"

class ReviewPagePublisher:
    def __init__(
        self,
        page_id: str | None = None,
        access_token: str | None = None,
        graph_version: str | None = None,
    ):
        self.page_id = page_id or os.getenv("FACEBOOK_PAGE_ID")
        self.access_token = access_token or os.getenv(
            "FACEBOOK_PAGE_ACCESS_TOKEN")
        if not self.page_id or not self.access_token:
            raise RuntimeError(
                "FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN must be"
                " configured.")
        self.graph_version = (
            graph_version or os.getenv("FACEBOOK_GRAPH_VERSION")
            or DEFAULT_GRAPH_VERSION)
        # httpx/httpcore log full request lines at INFO/DEBUG: pin them
        # to WARNING. The token travels in the request body only.
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)

    async def publish_photo(self, image_url: str, caption: str) -> str:
        """Publish one photo post to the configured page and return its
        post id. Raises only PublishRejected or PublishUncertain."""
        payload = {
            "url": image_url,
            "message": caption,
            "access_token": self.access_token,
            "published": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://graph.facebook.com/{self.graph_version}"
                    f"/{self.page_id}/photos",
                    data=payload,
                )
        except httpx.HTTPError as exc:
            raise PublishUncertain(
                f"publish_photo: transport error ({type(exc).__name__})"
            ) from None
        if 400 <= response.status_code < 500:
            try:
                data = response.json()
            except Exception:
                data = None
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                label = (
                    "publish_photo: facebook rejected"
                    f" HTTP {response.status_code}")
                code = error.get("code")
                if isinstance(code, int):
                    label += f" (graph error code {code})"
                raise PublishRejected(label) from None
            # a 4xx without a parseable Graph error body does not prove
            # the post was refused: treat it as uncertain
            raise PublishUncertain(
                f"publish_photo: facebook HTTP {response.status_code}"
                " with an unreadable error body") from None
        if response.status_code != 200:
            raise PublishUncertain(
                f"publish_photo: facebook HTTP {response.status_code}"
            ) from None
        try:
            data = response.json()
        except Exception:
            raise PublishUncertain(
                "publish_photo: unreadable ok response") from None
        post_id = None
        if isinstance(data, dict):
            post_id = data.get("post_id") or data.get("id")
        if not isinstance(post_id, str) or not post_id.strip():
            raise PublishUncertain(
                "publish_photo: ok response without a usable post id"
            ) from None
        return post_id