import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Profile
from app.services import notification_service

router = APIRouter(prefix="/notifications")


@router.get("")
async def list_notifications(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await notification_service.list_notifications(db, user.id)


@router.get("/unread-count")
async def unread_count(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"count": await notification_service.unread_count(db, user.id)}


@router.post("/read-all")
async def read_all(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await notification_service.mark_all_read(db, user.id)
    return {"ok": True}


@router.post("/{notif_id}/read")
async def read_one(notif_id: str, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await notification_service.mark_read(db, user.id, uuid.UUID(notif_id))
    return {"ok": True}
