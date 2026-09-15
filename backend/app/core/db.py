from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()


def _normalize_async_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver.

    Supabase/most tools hand out `postgresql://...` (which SQLAlchemy routes to
    the sync psycopg2 driver). We force the async driver so a plain paste works.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


# Engine is created only when DATABASE_URL is configured, so the app still
# boots (and the /api/health chip works) before the DB is wired up.
engine = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

if settings.database_url:
    db_url = _normalize_async_url(settings.database_url)

    connect_args: dict = {"statement_cache_size": 0}  # pgbouncer/transaction-pooler safe
    # Supabase (and most hosted Postgres) require SSL; local dev usually doesn't.
    if "localhost" not in db_url and "127.0.0.1" not in db_url:
        connect_args["ssl"] = "require"

    engine = create_async_engine(
        db_url,
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
