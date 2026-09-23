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
        # pgbouncer-safe: no persistent server-side prepared statements, and a
        # unique name per statement so a reused connection never collides.
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4().hex}__",
    }
    if not is_local:
        connect_args["ssl"] = "require"

    # Supabase's TRANSACTION pooler (port 6543 / pgbouncer) is only reliable with
    # NullPool (a fresh connection per checkout). A DIRECT or SESSION pooler
    # connection (port 5432) supports a real reusing pool, which is much faster —
    # so we auto-pick based on the port.
    is_txn_pooler = ":6543" in db_url

    if is_txn_pooler:
        engine = create_async_engine(db_url, poolclass=NullPool, connect_args=connect_args)
    else:
        engine = create_async_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
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
