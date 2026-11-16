import base64
import os
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash-image"


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    extension: str


class DesignImageAgent:
    async def generate(self, design_prompt: str) -> GeneratedImage:
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("DESIGN_IMAGE_MODEL", DEFAULT_MODEL)
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY must be configured.")

        # Image-only models (FLUX, Recraft, etc.) need ["image"].
        # Models that return text + image (Gemini) need ["image", "text"].
        modalities_env = os.getenv("DESIGN_IMAGE_MODALITIES", "image,text")
        modalities = [m.strip() for m in modalities_env.split(",") if m.strip()]

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": design_prompt}],
            "modalities": modalities,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            if response.is_error:
                raise RuntimeError(
                    f"OpenRouter {response.status_code} for model '{model}': {response.text}"
                )
            body = response.json()

        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                f"The design image model returned an invalid response: {body}"
            ) from error
        if not isinstance(message, dict):
            raise RuntimeError("The design image model returned an invalid message.")

        image_parts = message.get("images") or message.get("content") or []
        if not isinstance(image_parts, list):
            raise RuntimeError("The design image model returned no image parts.")

        image_url = next(
            (
                part["image_url"]["url"]
                for part in image_parts
                if isinstance(part, dict)
                and part.get("type") == "image_url"
                and isinstance(part.get("image_url"), dict)
                and isinstance(part["image_url"].get("url"), str)
            ),
            None,
        )
        if not image_url:
            raise RuntimeError("The design image model returned no image.")

        if image_url.startswith("data:"):
            metadata, encoded = image_url.split(",", 1)
            extension = "jpeg" if "jpeg" in metadata or "jpg" in metadata else "png"
            return GeneratedImage(base64.b64decode(encoded), extension)

        async with httpx.AsyncClient(timeout=120) as client:
            image_response = await client.get(image_url)
            image_response.raise_for_status()
        content_type = image_response.headers.get("content-type", "")
        extension = "jpeg" if "jpeg" in content_type else "png"
        return GeneratedImage(image_response.content, extension)


design_image_agent = DesignImageAgent()