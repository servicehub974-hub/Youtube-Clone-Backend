import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_actor
from app.core.anon import Actor
from app.core.db import get_db
from app.schemas.comment import CommentIn, CommentOut
from app.services import comment_service, feature_service
from app.services.comment_service import CommentError

router = APIRouter()


async def _require_anon_comments(actor: Actor, db: AsyncSession):
    if actor.user_id is None and not await feature_service.is_enabled(db, "anonymous_comments"):
        raise HTTPException(401, "Please sign in to comment.")


async def _require_anon_likes(actor: Actor, db: AsyncSession):
    if actor.user_id is None and not await feature_service.is_enabled(db, "anonymous_likes"):
        raise HTTPException(401, "Please sign in to like.")


@router.get("/content/{content_id}/comments", response_model=list[CommentOut])
async def list_comments(
    content_id: str,
    sort: str = "top",
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    return await comment_service.list_comments(db, uuid.UUID(content_id), actor, sort)


@router.post("/content/{content_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(
    content_id: str,
    data: CommentIn,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    await _require_anon_comments(actor, db)
    try:
        return await comment_service.create_comment(
            db, uuid.UUID(content_id), actor, data.body,
            uuid.UUID(data.parent_id) if data.parent_id else None, data.anon_name,
        )
    except CommentError as e:
        raise HTTPException(400, detail=str(e))


@router.get("/comments/{comment_id}/replies", response_model=list[CommentOut])
async def list_replies(
    comment_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    return await comment_service.list_replies(db, uuid.UUID(comment_id), actor)


@router.post("/comments/{comment_id}/like")
async def like_comment(
    comment_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    await _require_anon_likes(actor, db)
    liked, count = await comment_service.toggle_comment_like(db, uuid.UUID(comment_id), actor)
    return {"liked": liked, "like_count": count}


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    try:
        await comment_service.delete_comment(db, uuid.UUID(comment_id), actor)
    except CommentError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}


@router.post("/comments/{comment_id}/pin")
async def pin_comment(
    comment_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    try:
        pinned = await comment_service.toggle_pin(db, uuid.UUID(comment_id), actor)
    except CommentError as e:
        raise HTTPException(403, detail=str(e))
    return {"pinned": pinned}
