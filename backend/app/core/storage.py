"""
Storage abstraction — swap providers via config only.

Frontend flow is provider-agnostic: it asks the backend for a signed upload
target, PUTs the file straight there, then sends back the returned public URL.
To migrate Supabase Storage -> Backblaze B2 / Cloudflare R2 later, implement
B2StorageProvider and set STORAGE_PROVIDER=b2 — no frontend changes.
"""
import httpx

from app.core.config import get_settings

settings = get_settings()


class StorageProvider:
    async def create_signed_upload(self, path: str, content_type: str) -> dict:
        raise NotImplementedError

    def public_url(self, path: str) -> str:
        raise NotImplementedError


class SupabaseStorageProvider(StorageProvider):
    def __init__(self) -> None:
        self.base = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_role_key
        self.bucket = settings.storage_bucket

    async def create_signed_upload(self, path: str, content_type: str) -> dict:
        url = f"{self.base}/storage/v1/object/upload/sign/{self.bucket}/{path}"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {self.key}", "apikey": self.key},
            )
            r.raise_for_status()
            signed = r.json()["url"]  # relative: /object/upload/sign/<bucket>/<path>?token=...
        return {
            "method": "PUT",
            "upload_url": f"{self.base}/storage/v1{signed}",
            "headers": {"Content-Type": content_type, "x-upsert": "true"},
            "public_url": self.public_url(path),
        }

    def public_url(self, path: str) -> str:
        if settings.storage_public_base:
            return f"{settings.storage_public_base.rstrip('/')}/{path}"
        return f"{self.base}/storage/v1/object/public/{self.bucket}/{path}"


class B2StorageProvider(StorageProvider):
    """Placeholder — implement S3 presigned PUT when migrating to Backblaze B2/R2.

    create a boto3/aioboto3 client with the B2 S3-compatible endpoint and return
    a presigned PUT url + the Cloudflare/B2 public url. Frontend stays the same.
    """

    async def create_signed_upload(self, path: str, content_type: str) -> dict:
        raise NotImplementedError("B2 storage not configured yet.")

    def public_url(self, path: str) -> str:
        base = settings.storage_public_base.rstrip("/") if settings.storage_public_base else ""
        return f"{base}/{path}"


def get_storage() -> StorageProvider:
    if settings.storage_provider == "b2":
        return B2StorageProvider()
    return SupabaseStorageProvider()
