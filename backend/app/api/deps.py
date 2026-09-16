import logging

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.supabase_auth import verify_supabase_token
from app.models import Profile
from app.services import user_service

logger = logging.getLogger("auth")


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    try:
        claims = verify_supabase_token(token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return await user_service.get_or_create_profile(
        db, claims["sub"], claims.get("email")
    )


async def require_admin(user: Profile = Depends(get_current_user)) -> Profile:
    if not user.role or user.role.name != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def require_role(*roles: str):
    async def checker(user: Profile = Depends(get_current_user)) -> Profile:
        role_name = user.role.name if user.role else "user"
        if role_name not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed")
        return user

    return checker


async def get_current_user_optional(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Profile | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        claims = verify_supabase_token(token)
        return await user_service.get_or_create_profile(db, claims["sub"], claims.get("email"))
    except Exception:
        return None


def require_feature(key: str):
    """Dependency: 403 if the given feature flag is disabled."""
    from fastapi import HTTPException, status
    from app.services import feature_service

    async def dep(db: AsyncSession = Depends(get_db)) -> None:
        if not await feature_service.is_enabled(db, key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This feature is currently disabled.")

    return dep
