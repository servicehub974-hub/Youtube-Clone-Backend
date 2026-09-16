import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.models import Profile
from app.schemas.comment import CommentIn, CommentOut
from app.services import comment_service
from app.services.comment_service import CommentError

router = APIRouter()


@router.get("/content/{content_id}/comments", response_model=list[CommentOut])
async def list_comments(
    content_id: str,
    sort: str = Query("top"),
    user: Profile | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    return await comment_service.list_comments(
        db, uuid.UUID(content_id), user.id if user else None, sort
    )


@router.post("/content/{content_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(
    content_id: str,
    data: CommentIn,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await comment_service.create_comment(
            db,
            uuid.UUID(content_id),
            user.id,
            data.body,
            uuid.UUID(data.parent_id) if data.parent_id else None,
        )
    except CommentError as e:
        raise HTTPException(400, detail=str(e))


@router.get("/comments/{comment_id}/replies", response_model=list[CommentOut])
async def list_replies(
    comment_id: str,
    user: Profile | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    return await comment_service.list_replies(
        db, uuid.UUID(comment_id), user.id if user else None
    )


@router.post("/comments/{comment_id}/like")
async def like_comment(
    comment_id: str,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    liked, count = await comment_service.toggle_comment_like(
        db, uuid.UUID(comment_id), user.id
    )
    return {"liked": liked, "like_count": count}


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await comment_service.delete_comment(db, uuid.UUID(comment_id), user)
    except CommentError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}


@router.post("/comments/{comment_id}/pin")
async def pin_comment(
    comment_id: str,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        pinned = await comment_service.toggle_pin(db, uuid.UUID(comment_id), user)
    except CommentError as e:
        raise HTTPException(403, detail=str(e))
    return {"pinned": pinned}
