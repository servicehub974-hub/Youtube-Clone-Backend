import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.db import get_db
from app.models import Profile
from app.schemas.user import RoleUpdate, UserOut
from app.services import user_service
from app.services.user_service import UserError, to_user_out

router = APIRouter(prefix="/admin")

VALID_ROLES = {"user", "creator", "admin"}


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    profiles = await user_service.list_profiles(db, limit=100)
    return [to_user_out(p) for p in profiles]


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(
    user_id: str,
    data: RoleUpdate,
    _admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if data.role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    try:
        updated = await user_service.set_role(db, uuid.UUID(user_id), data.role)
    except (UserError, ValueError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return to_user_out(updated)
