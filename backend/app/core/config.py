from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "NEXUS API"
    environment: str = "development"
    version: str = "0.1.0"

    # Comma-separated list of allowed browser origins for CORS.
    cors_origins: str = "http://localhost:3000"

    # Supabase Postgres connection string (plain postgresql:// is auto-upgraded).
    database_url: str = ""

    # --- Supabase Auth ---
    # From Supabase → Settings → API.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""          # "JWT Secret" (legacy) — verifies access tokens
    supabase_service_role_key: str = ""    # used for storage signed uploads + admin

    # --- Storage (provider-agnostic) ---
    storage_provider: str = "supabase"   # "supabase" | "b2"
    storage_bucket: str = "media"
    storage_public_base: str = ""        # optional CDN/base override (e.g. Cloudflare in front of B2)

    # Backblaze B2 (S3-compatible). Set STORAGE_PROVIDER=b2 to use.
    b2_key_id: str = ""
    b2_app_key: str = ""
    b2_bucket: str = ""
    b2_endpoint: str = ""                # e.g. https://s3.us-west-004.backblazeb2.com
    b2_region: str = "us-west-004"

    # --- Roles ---
    # If True, users can self-upgrade to creator. If False, it becomes an
    # admin-approved flow (added later).
    allow_self_creator: bool = True

    # Signing secret for anonymous-visitor cookies
    anon_secret: str = "dev-anon-secret-change-me"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
