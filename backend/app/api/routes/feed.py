from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.core.db import get_db
from app.models import Profile
from app.services import feed_service

router = APIRouter(prefix="/feed")


@router.get("")
async def mixed(offset: int = Query(0, ge=0), viewer: Profile | None = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
    items, nxt = await feed_service.posts_feed(db, viewer.id if viewer else None, offset)
    return {"items": items, "next_offset": nxt}
