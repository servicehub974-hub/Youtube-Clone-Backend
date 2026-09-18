import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()


def _normalize_async_url(url: str) -> str:
    """Force the asyncpg driver so a plain `postgresql://` paste works."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


engine = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

if settings.database_url:
    db_url = _normalize_async_url(settings.database_url)
    is_local = "localhost" in db_url or "127.0.0.1" in db_url

    connect_args: dict = {
        # Supabase transaction pooler (pgbouncer) doesn't keep prepared
        # statements — disable asyncpg's cache and give each statement a unique
        # name so a reused pooled connection never collides.
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4().hex}__",
    }
    if not is_local:
        connect_args["ssl"] = "require"

    # Real connection pool — reuse connections across requests (much faster than
    # opening a fresh SSL connection every time). SQLAlchemy's compiled-SQL cache
    # is left ON for speed; only asyncpg's server-side prepared cache is disabled.
    engine = create_async_engine(
        db_url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,   # recycle conns every 30 min (avoids stale pooler conns)
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with AsyncSessionLocal() as session:
        yield session
