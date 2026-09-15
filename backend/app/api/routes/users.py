from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Profile
from app.schemas.user import ProfileUpdate, UserOut
from app.services import user_service
from app.services.user_service import to_user_out

router = APIRouter(prefix="/users")
settings = get_settings()


@router.get("/me", response_model=UserOut)
async def me(user: Profile = Depends(get_current_user)):
    return to_user_out(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    data: ProfileUpdate,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await user_service.update_profile(db, user, data)
    updated.email = getattr(user, "email", None)
    return to_user_out(updated)


@router.post("/me/become-creator", response_model=UserOut)
async def become_creator(
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.allow_self_creator:
        # If self-serve is disabled, this would become an application/approval
        # flow handled by admins. For now just return current state.
        return to_user_out(user)
    updated = await user_service.become_creator(db, user)
    return to_user_out(updated)
