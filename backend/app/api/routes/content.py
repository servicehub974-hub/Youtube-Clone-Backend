from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_actor, get_current_user, require_role
from app.core.anon import Actor
from app.services import feature_service
from app.core.db import get_db
from app.models import Profile
import uuid

from app.schemas.content import ContentCardOut, ContentDetailOut, ContentIn, ContentUpdate, FeedOut
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


@router.get("/content/{content_id}", response_model=ContentDetailOut)
async def get_content(
    content_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    try:
        cid = uuid.UUID(content_id)
    except ValueError:
        raise HTTPException(404, "Not found")
    detail = await content_service.get_detail(db, cid, actor.user_id, actor.anon_id)
    if not detail:
        raise HTTPException(404, "Content not found")
    return detail


@router.post("/content/{content_id}/like")
async def like_content(
    content_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    if actor.user_id is None and not await feature_service.is_enabled(db, "anonymous_likes"):
        raise HTTPException(401, "Please sign in to like.")
    liked, count = await content_service.toggle_like(db, uuid.UUID(content_id), actor)
    return {"liked": liked, "like_count": count}


@router.post("/content/{content_id}/dislike")
async def dislike_content(
    content_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    if actor.user_id is None and not await feature_service.is_enabled(db, "anonymous_likes"):
        raise HTTPException(401, "Please sign in to react.")
    disliked, count = await content_service.toggle_dislike(db, uuid.UUID(content_id), actor)
    return {"disliked": disliked, "like_count": count}


@router.patch("/content/{content_id}", response_model=ContentDetailOut)
async def update_content(
    content_id: str,
    data: ContentUpdate,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    try:
        await content_service.update_content(
            db, uuid.UUID(content_id), user, data.model_dump(exclude_unset=True)
        )
    except PermissionError:
        raise HTTPException(403, "Not allowed")
    except ValueError as e:
        raise HTTPException(404, str(e))
    detail = await content_service.get_detail(db, uuid.UUID(content_id), user.id)
    return detail


@router.delete("/content/{content_id}")
async def delete_content(
    content_id: str,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    try:
        await content_service.delete_content(db, uuid.UUID(content_id), user)
    except PermissionError:
        raise HTTPException(403, "Not allowed")
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}
