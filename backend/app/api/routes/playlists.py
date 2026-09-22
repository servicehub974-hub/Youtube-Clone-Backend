import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.models import Profile
from app.schemas.playlist import (
    AddItemIn, PlaylistDetailOut, PlaylistIn, PlaylistOut, PlaylistUpdate, ReorderIn,
)
from app.services import playlist_service
from app.services.playlist_service import PlaylistError

router = APIRouter(prefix="/playlists")


@router.get("/mine", response_model=list[PlaylistOut])
async def my_playlists(
    content_id: str | None = None,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = uuid.UUID(content_id) if content_id else None
    return await playlist_service.list_my(db, user.id, cid)


@router.post("", response_model=PlaylistOut, status_code=201)
async def create_playlist(
    data: PlaylistIn,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await playlist_service.create_playlist(db, user.id, data)
    return await playlist_service.out(db, p)


@router.get("/{playlist_id}", response_model=PlaylistDetailOut)
async def get_playlist(
    playlist_id: str,
    viewer: Profile | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    detail = await playlist_service.get_detail(db, uuid.UUID(playlist_id), viewer.id if viewer else None)
    if not detail:
        raise HTTPException(404, "Playlist not found")
    return detail


@router.patch("/{playlist_id}")
async def update_playlist(
    playlist_id: str,
    data: PlaylistUpdate,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await playlist_service.update_playlist(db, uuid.UUID(playlist_id), user.id, data)
    except PlaylistError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}


@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: str,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await playlist_service.delete_playlist(db, uuid.UUID(playlist_id), user.id)
    except PlaylistError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}


@router.post("/{playlist_id}/items")
async def add_item(
    playlist_id: str,
    data: AddItemIn,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await playlist_service.add_item(db, uuid.UUID(playlist_id), user.id, uuid.UUID(data.content_id))
    except PlaylistError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}


@router.delete("/{playlist_id}/items/{content_id}")
async def remove_item(
    playlist_id: str,
    content_id: str,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await playlist_service.remove_item(db, uuid.UUID(playlist_id), user.id, uuid.UUID(content_id))
    except PlaylistError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}


@router.post("/{playlist_id}/reorder")
async def reorder(
    playlist_id: str,
    data: ReorderIn,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await playlist_service.reorder(db, uuid.UUID(playlist_id), user.id, data.content_ids)
    except PlaylistError as e:
        raise HTTPException(403, detail=str(e))
    return {"ok": True}
