import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.db import get_db
from app.models import Profile
from app.schemas.user import RoleUpdate, UserOut
from app.services import feature_service, user_service, admin_service
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


from pydantic import BaseModel as _BaseModel


class _FlagIn(_BaseModel):
    enabled: bool


@router.get("/features")
async def admin_features(
    _admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await feature_service.get_flags(db)


@router.patch("/features/{key}")
async def set_feature(
    key: str,
    data: _FlagIn,
    _admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    enabled = await feature_service.set_flag(db, key, data.enabled)
    from app.core.cache import invalidate
    invalidate("features:")
    return {"key": key, "enabled": enabled}


from pydantic import BaseModel as _BaseModel


class _Ban(_BaseModel):
    banned: bool


class _Site(_BaseModel):
    name: str = "NEXUS PRO"
    logo_url: str | None = None
    favicon_url: str | None = None
    tagline: str | None = None


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: str, data: _Ban, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.ban_user(db, admin, uuid.UUID(user_id), data.banned)


@router.get("/reports")
async def reports(status: str = "open", admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.list_reports(db, status or None)


@router.post("/reports/{report_id}/dismiss")
async def dismiss_report(report_id: str, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.resolve_report(db, admin, uuid.UUID(report_id), dismiss=True)


@router.post("/reports/{report_id}/takedown")
async def takedown_report(report_id: str, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.takedown(db, admin, uuid.UUID(report_id))


@router.post("/content/{content_id}/restore")
async def restore_content(content_id: str, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.restore_content(db, admin, uuid.UUID(content_id))


@router.get("/hidden-content")
async def hidden_content(admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.hidden_content(db)


@router.get("/analytics")
async def analytics(admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.analytics(db)


@router.get("/audit")
async def audit(admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await admin_service.list_audit(db)


@router.put("/site")
async def set_site(data: _Site, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.core.cache import invalidate
    res = await admin_service.set_site(db, admin, data.name, data.logo_url, data.favicon_url, data.tagline)
    invalidate("site:")
    return res
