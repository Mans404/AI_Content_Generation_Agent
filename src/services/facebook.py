import os
import logging
from uuid import UUID

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from src.database.companies import async_session_factory
from src.models.companies import FacebookPageModel

logger = logging.getLogger(__name__)

# Use whichever Graph API version is current in your Meta app dashboard.
GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "v21.0")
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
_fernet = Fernet(os.environ["FACEBOOK_TOKEN_KEY"])

# Graph error codes where retrying is pointless (bad token, missing permission, bad params).
_PERMANENT_CODES = {10, 100, 190, 200}


class PermanentPublishError(Exception):
    """Retrying will not help (expired token, missing permission, no connection...)."""


def encrypt_token(token: str) -> str:
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()


def _raise_for_graph_error(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error")
    if response.is_success and not error:
        return body
    code = (error or {}).get("code")
    message = (error or {}).get("message") or f"HTTP {response.status_code}"
    text = f"Facebook error {code}: {message}"
    if code in _PERMANENT_CODES:
        raise PermanentPublishError(text)
    raise RuntimeError(text)  # transient (rate limit, 5xx...) -> worker retries


async def verify_page(page_id: str, token: str) -> str:
    """Return the page name if the token can access the page."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{GRAPH_URL}/{page_id}",
            params={"fields": "name", "access_token": token},
        )
    return _raise_for_graph_error(response)["name"]


class FacebookPublisher:
    async def publish(self, image_url: str, caption: str, company_id: UUID) -> str:
        async with async_session_factory() as session:
            page = await session.scalar(
                select(FacebookPageModel).where(FacebookPageModel.company_id == company_id)
            )
        if page is None:
            raise PermanentPublishError("No Facebook Page is connected.")

        token = decrypt_token(page.access_token_encrypted)
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{GRAPH_URL}/{page.page_id}/photos",
                data={  # token in the body so it never appears in URL logs
                    "url": image_url,
                    "caption": caption,
                    "published": "true",
                    "access_token": token,
                },
            )
        body = _raise_for_graph_error(response)
        return body.get("post_id") or body["id"]