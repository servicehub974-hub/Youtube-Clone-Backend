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
    """Backblaze B2 via its S3-compatible API (boto3 presigned PUT).

    The browser PUTs the file straight to B2 with the presigned URL — nothing
    large ever passes through the backend. Reads use a public bucket URL (or a
    Cloudflare/CDN base set via STORAGE_PUBLIC_BASE).
    """

    def __init__(self) -> None:
        import boto3
        from botocore.client import Config

        self.bucket = settings.b2_bucket
        self.endpoint = settings.b2_endpoint.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=settings.b2_key_id,
            aws_secret_access_key=settings.b2_app_key,
            region_name=settings.b2_region,
            config=Config(signature_version="s3v4"),
        )

    async def create_signed_upload(self, path: str, content_type: str) -> dict:
        # Content-Type is NOT part of the signature (more forgiving); the browser
        # still sends it and B2 stores it as the object's content type.
        url = self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": path},
            ExpiresIn=3600,
            HttpMethod="PUT",
        )
        return {
            "method": "PUT",
            "upload_url": url,
            "headers": {"Content-Type": content_type},
            "public_url": self.public_url(path),
        }

    def public_url(self, path: str) -> str:
        if settings.storage_public_base:
            return f"{settings.storage_public_base.rstrip('/')}/{path}"
        host = self.endpoint.replace("https://", "").replace("http://", "")
        return f"https://{self.bucket}.{host}/{path}"


_provider: StorageProvider | None = None


def get_storage() -> StorageProvider:
    global _provider
    if _provider is None:
        _provider = B2StorageProvider() if settings.storage_provider == "b2" else SupabaseStorageProvider()
    return _provider
