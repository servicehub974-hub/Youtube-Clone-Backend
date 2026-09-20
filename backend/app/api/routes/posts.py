import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.models import Profile
from app.schemas.post import (
    PostCommentIn, PostCommentOut, PostCreate, PostFeedOut, PostOut, PostUpdate,
)
from app.services import post_service
from app.services.post_service import PostError

router = APIRouter(prefix="/posts")


@router.get("", response_model=PostFeedOut)
async def feed(cursor: str | None = None, viewer: Profile | None = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
    items, nxt = await post_service.feed(db, viewer.id if viewer else None, cursor)
    return PostFeedOut(items=items, next_cursor=nxt)


@router.post("", response_model=PostOut, status_code=201)
async def create(data: PostCreate, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        p = await post_service.create_post(db, user.id, data)
    except PostError as e:
        raise HTTPException(400, detail=str(e))
    return await post_service.to_out(db, p, user.id)


@router.get("/saved", response_model=list[PostOut])
async def saved_posts(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await post_service.list_saved(db, user.id)


@router.get("/liked", response_model=list[PostOut])
async def liked_posts(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await post_service.list_liked(db, user.id)


@router.get("/user/{user_id}", response_model=list[PostOut])
async def user_posts(user_id: str, viewer: Profile | None = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
    return await post_service.list_by_author(db, uuid.UUID(user_id), viewer.id if viewer else None)


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: str, viewer: Profile | None = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
    p = await post_service.get(db, uuid.UUID(post_id), viewer.id if viewer else None)
    if not p:
        raise HTTPException(404, "Post not found")
    return p


@router.patch("/{post_id}", response_model=PostOut)
async def edit_post(post_id: str, data: PostUpdate, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await post_service.update_post(db, uuid.UUID(post_id), user.id, data)
    except PostError as e:
        raise HTTPException(403, detail=str(e))


@router.delete("/{post_id}")
async def delete_post(post_id: str, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        await post_service.delete_post(db, uuid.UUID(post_id), user.id)
    except PostError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}


@router.post("/{post_id}/like")
async def like(post_id: str, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    liked, count = await post_service.toggle_like(db, uuid.UUID(post_id), user.id)
    return {"liked": liked, "count": count}


@router.post("/{post_id}/save")
async def save(post_id: str, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    saved = await post_service.toggle_save(db, uuid.UUID(post_id), user.id)
    return {"saved": saved}


@router.post("/{post_id}/repost", response_model=PostOut, status_code=201)
async def repost(post_id: str, data: PostCommentIn | None = None, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    body = data.body if data else None
    p = await post_service.create_post(db, user.id, PostCreate(body=body, repost_of=post_id))
    return await post_service.to_out(db, p, user.id)


@router.get("/{post_id}/comments", response_model=list[PostCommentOut])
async def comments(post_id: str, db: AsyncSession = Depends(get_db)):
    return await post_service.list_comments(db, uuid.UUID(post_id))


@router.post("/{post_id}/comments", response_model=PostCommentOut, status_code=201)
async def add_comment(post_id: str, data: PostCommentIn, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await post_service.add_comment(db, uuid.UUID(post_id), user.id, data.body)
