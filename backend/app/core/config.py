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

    # Supabase Postgres connection string (async driver).
    # e.g. postgresql+asyncpg://postgres:PASSWORD@HOST:5432/postgres
    database_url: str = ""

    # --- Auth ---
    jwt_secret: str = "dev-insecure-change-me"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    refresh_cookie_name: str = "nexus_refresh"
    # Local dev: secure=False, samesite="lax".
    # Cross-site prod (Vercel + Render): secure=True, samesite="none".
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # --- Frontend base URL (for building email links) ---
    frontend_url: str = "http://localhost:3000"

    # --- Email / SMTP (provider-agnostic) ---
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@example.com"
    smtp_from_name: str = "NEXUS"
    smtp_tls: bool = True   # STARTTLS — port 587
    smtp_ssl: bool = False  # implicit SSL — port 465

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
