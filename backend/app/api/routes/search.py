import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_actor
from app.core.cache import cached
from app.core.db import get_db
from app.core.anon import Actor
from app.schemas.content import ContentCardOut
from app.services import search_service

router = APIRouter(prefix="/search")


@router.get("", response_model=dict)
async def search_content(
    q: str = Query("", max_length=120),
    type: str | None = None,
    category: str | None = None,
    free: str | None = None,
    sort: str = "relevance",
    limit: int = Query(30, ge=1, le=60),
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    cards, count = await search_service.search(
        db, q, content_type=type, category=category, free=free, sort=sort, limit=limit
    )
    # log the search (also captures zero-result queries for admin analytics)
    if q.strip():
        try:
            await search_service.record(db, actor.user_id, actor.anon_id, q, count)
        except Exception:
            await db.rollback()
    return {"items": [c.model_dump() for c in cards], "count": count}


@router.get("/suggestions", response_model=list[str])
async def suggestions(q: str = "", db: AsyncSession = Depends(get_db)):
    async def build():
        return await search_service.suggestions(db, q)
    # cache short-lived per query prefix
    key = f"suggest:{q.strip().lower()}"
    return await cached(key, 20, build) if q.strip() else []


@router.get("/trending", response_model=list[str])
async def trending(db: AsyncSession = Depends(get_db)):
    return await cached("search:trending", 60, lambda: search_service.trending(db))


@router.get("/recent")
async def recent(actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    return await search_service.recent(db, actor.user_id, actor.anon_id)


@router.delete("/recent/{entry_id}")
async def delete_recent(entry_id: str, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    await search_service.delete_recent(db, uuid.UUID(entry_id), actor.user_id, actor.anon_id)
    return {"ok": True}
