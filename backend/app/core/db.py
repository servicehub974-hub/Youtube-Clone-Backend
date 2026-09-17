import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

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
        # Supabase transaction pooler (pgbouncer) does NOT support prepared
        # statements. Disable asyncpg's statement cache...
        "statement_cache_size": 0,
        # ...and give each prepared statement a unique name so pgbouncer never
        # sees a duplicate across pooled connections.
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
    }
    if not is_local:
        connect_args["ssl"] = "require"

    engine = create_async_engine(
        db_url,
        # NullPool: don't reuse connections across requests — required with the
        # pgbouncer transaction pooler.
        poolclass=NullPool,
        # Disable SQLAlchemy's own prepared-statement cache too.
        execution_options={"compiled_cache": None},
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
