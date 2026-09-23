from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.db import get_db
from app.models import Profile
from app.schemas.content import TagIn, TagOut
from app.services import content_service

router = APIRouter(prefix="/tags")


@router.get("", response_model=list[TagOut])
async def list_tags(db: AsyncSession = Depends(get_db)):
    tags = await content_service.list_tags(db, active_only=True)
    return [content_service.tag_out(t) for t in tags]


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(
    data: TagIn,
    _admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    tag = await content_service.create_tag(db, data)
    return content_service.tag_out(tag)
