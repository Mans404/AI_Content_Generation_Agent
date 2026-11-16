import asyncio
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

DOCTOR_IMAGES_BUCKET = "doctor-designs"
DESIGN_IMAGES_BUCKET = "doctor-designs"


class SupabaseStorage:
    def __init__(self) -> None:
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not url or not key:
                raise RuntimeError(
                    "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured."
                )
            self._client = create_client(url, key)
        return self._client

    async def upload(
        self,
        bucket: str,
        path: str,
        data: bytes,
        content_type: str,
    ) -> str:
        def upload_sync() -> str:
            storage = self._get_client().storage.from_(bucket)
            storage.upload(
                path,
                data,
                {"content-type": content_type, "upsert": "false"},
            )
            return storage.get_public_url(path)

        return await asyncio.to_thread(upload_sync)

    async def delete(self, bucket: str, path: str) -> None:
        await asyncio.to_thread(
            lambda: self._get_client().storage.from_(bucket).remove([path])
        )

    async def move(self, bucket: str, source: str, destination: str) -> None:
        await asyncio.to_thread(
            lambda: self._get_client().storage.from_(bucket).move(source, destination)
        )

    async def size(self, bucket: str, path: str) -> int:
        data = await asyncio.to_thread(
            lambda: self._get_client().storage.from_(bucket).download(path)
        )
        return len(data)

    def public_url(self, bucket: str, path: str) -> str:
        return self._get_client().storage.from_(bucket).get_public_url(path)


def storage_path_from_url(url: str, bucket: str) -> str | None:
    path = urlsplit(url).path
    marker = f"/storage/v1/object/public/{bucket}/"
    if marker not in path:
        return None
    return path.split(marker, 1)[1]


def filename_from_path(path: str) -> str:
    return urlsplit(path).path.rsplit("/", 1)[-1]


supabase_storage = SupabaseStorage()
