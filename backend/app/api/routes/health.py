from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
    }


@router.get("/health/db")
async def health_db():
    """Reports whether the database is reachable. Never raises."""
    settings = get_settings()
    if not settings.database_url:
        return {"database": "not_configured"}
    try:
        from app.core.db import AsyncSessionLocal

        if AsyncSessionLocal is None:
            return {"database": "not_configured"}
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"database": "connected"}
    except Exception as exc:  # noqa: BLE001 — surface any connection error
        return {"database": "error", "detail": str(exc)[:200]}
