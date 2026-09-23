import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cache import cached
from app.core.db import get_db
from app.models import Profile
from app.services import admin_service

router = APIRouter()


class ReportIn(BaseModel):
    target_type: str
    target_id: str
    reason: str | None = None


@router.get("/site")
async def site(db: AsyncSession = Depends(get_db)):
    return await cached("site:settings", 60, lambda: admin_service.get_site(db))


@router.post("/report")
async def report(data: ReportIn, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await admin_service.create_report(db, user.id, data.target_type, uuid.UUID(data.target_id), data.reason)
