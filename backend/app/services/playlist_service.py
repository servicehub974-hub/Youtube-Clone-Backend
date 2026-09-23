import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Content, Playlist, PlaylistItem, Profile
from app.schemas.playlist import PlaylistDetailOut, PlaylistIn, PlaylistOut, PlaylistUpdate
from app.services.content_service import to_card


class PlaylistError(Exception):
    pass


async def _count(db: AsyncSession, playlist_id: uuid.UUID) -> int:
    r = await db.execute(
        select(func.count()).select_from(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id)
    )
    return int(r.scalar_one())


async def _first_thumb(db: AsyncSession, playlist_id: uuid.UUID) -> str | None:
    r = await db.execute(
        select(Content.thumbnail_url).join(PlaylistItem, PlaylistItem.content_id == Content.id)
        .where(PlaylistItem.playlist_id == playlist_id)
        .order_by(PlaylistItem.position).limit(1)
    )
    return r.scalar_one_or_none()


async def _owned(db: AsyncSession, playlist_id: uuid.UUID, owner_id: uuid.UUID) -> Playlist:
    p = (await db.execute(select(Playlist).where(Playlist.id == playlist_id))).scalar_one_or_none()
    if not p:
        raise PlaylistError("Playlist not found")
    if p.owner_id != owner_id:
        raise PlaylistError("Not allowed")
    return p


async def create_playlist(db: AsyncSession, owner_id: uuid.UUID, data: PlaylistIn) -> Playlist:
    p = Playlist(owner_id=owner_id, title=data.title, description=data.description,
                 visibility=data.visibility if data.visibility in ("public", "unlisted", "private") else "public")
    db.add(p)
    await db.commit()
    return (await db.execute(select(Playlist).where(Playlist.id == p.id))).scalar_one()


async def update_playlist(db: AsyncSession, playlist_id: uuid.UUID, owner_id: uuid.UUID, data: PlaylistUpdate):
    p = await _owned(db, playlist_id, owner_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(p, k, v)
    await db.commit()
    return p


async def delete_playlist(db: AsyncSession, playlist_id: uuid.UUID, owner_id: uuid.UUID):
    p = await _owned(db, playlist_id, owner_id)
    await db.delete(p)
    await db.commit()


async def out(db: AsyncSession, p: Playlist, content_id: uuid.UUID | None = None) -> PlaylistOut:
    contains = False
    if content_id is not None:
        contains = (await db.execute(
            select(PlaylistItem).where(PlaylistItem.playlist_id == p.id, PlaylistItem.content_id == content_id)
        )).scalar_one_or_none() is not None
    return PlaylistOut(
        id=str(p.id), title=p.title, description=p.description, visibility=p.visibility,
        item_count=await _count(db, p.id), thumbnail=await _first_thumb(db, p.id),
        owner_id=str(p.owner_id), contains=contains,
    )


async def list_my(db: AsyncSession, owner_id: uuid.UUID, content_id: uuid.UUID | None = None) -> list[PlaylistOut]:
    pls = (await db.execute(
        select(Playlist).where(Playlist.owner_id == owner_id).order_by(Playlist.updated_at.desc())
    )).scalars().all()
    return [await out(db, p, content_id) for p in pls]


async def list_public(db: AsyncSession, owner_id: uuid.UUID) -> list[PlaylistOut]:
    pls = (await db.execute(
        select(Playlist).where(Playlist.owner_id == owner_id, Playlist.visibility == "public")
        .order_by(Playlist.updated_at.desc())
    )).scalars().all()
    return [await out(db, p) for p in pls]


async def get_detail(db: AsyncSession, playlist_id: uuid.UUID, viewer_id: uuid.UUID | None) -> PlaylistDetailOut | None:
    p = (await db.execute(select(Playlist).where(Playlist.id == playlist_id))).scalar_one_or_none()
    if not p:
        return None
    if p.visibility == "private" and p.owner_id != viewer_id:
        return None
    rows = (await db.execute(
        select(Content).join(PlaylistItem, PlaylistItem.content_id == Content.id)
        .where(PlaylistItem.playlist_id == playlist_id).order_by(PlaylistItem.position)
    )).scalars().all()
    owner = (await db.execute(select(Profile).where(Profile.id == p.owner_id))).scalar_one_or_none()
    return PlaylistDetailOut(
        id=str(p.id), title=p.title, description=p.description, visibility=p.visibility,
        owner_id=str(p.owner_id),
        owner_name=(owner.display_name or owner.username or "User") if owner else "User",
        is_owner=viewer_id == p.owner_id,
        items=[to_card(c) for c in rows],
    )


async def add_item(db: AsyncSession, playlist_id: uuid.UUID, owner_id: uuid.UUID, content_id: uuid.UUID):
    await _owned(db, playlist_id, owner_id)
    exists = (await db.execute(
        select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id, PlaylistItem.content_id == content_id)
    )).scalar_one_or_none()
    if exists:
        return
    maxpos = (await db.execute(
        select(func.coalesce(func.max(PlaylistItem.position), -1)).where(PlaylistItem.playlist_id == playlist_id)
    )).scalar_one()
    db.add(PlaylistItem(playlist_id=playlist_id, content_id=content_id, position=int(maxpos) + 1))
    await db.commit()


async def remove_item(db: AsyncSession, playlist_id: uuid.UUID, owner_id: uuid.UUID, content_id: uuid.UUID):
    await _owned(db, playlist_id, owner_id)
    row = (await db.execute(
        select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id, PlaylistItem.content_id == content_id)
    )).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


async def reorder(db: AsyncSession, playlist_id: uuid.UUID, owner_id: uuid.UUID, content_ids: list[str]):
    await _owned(db, playlist_id, owner_id)
    for i, cid in enumerate(content_ids):
        try:
            item = (await db.execute(
                select(PlaylistItem).where(
                    PlaylistItem.playlist_id == playlist_id, PlaylistItem.content_id == uuid.UUID(cid)
                )
            )).scalar_one_or_none()
            if item:
                item.position = i
        except ValueError:
            continue
    await db.commit()
