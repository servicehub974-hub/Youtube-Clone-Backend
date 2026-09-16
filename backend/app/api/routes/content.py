from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models import Profile
from app.schemas.content import ContentCardOut, ContentIn, FeedOut
from app.services import content_service

router = APIRouter()


@router.get("/content", response_model=FeedOut)
async def list_content(
    limit: int = Query(12, ge=1, le=50),
    cursor: str | None = None,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    items, next_cursor = await content_service.list_feed(db, limit, cursor, category)
    return FeedOut(items=items, next_cursor=next_cursor)


@router.post("/content", response_model=ContentCardOut, status_code=201)
async def create_content(
    data: ContentIn,
    user: Profile = Depends(require_role("creator", "admin")),
    db: AsyncSession = Depends(get_db),
):
    content = await content_service.create_content(db, user.id, data)
    return content_service.to_card(content)


@router.get("/content/mine", response_model=list[ContentCardOut])
async def my_content(
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await content_service.list_by_owner(db, user.id)
    return [content_service.to_card(c) for c in rows]
