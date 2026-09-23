import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cache import cached
from app.core.db import get_db
from app.models import Profile
from app.services import admin_service
from app.models import Review, Profile as _Profile

router = APIRouter()


class ReviewIn(BaseModel):
    rating: int = 5
    body: str | None = None


class ReportIn(BaseModel):
    target_type: str
    target_id: str
    reason: str | None = None


@router.get("/site")
async def site(db: AsyncSession = Depends(get_db)):
    return await cached("site:settings", 60, lambda: admin_service.get_site(db))


@router.post("/report")
async def report(data: ReportIn, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await admin_service.create_report(db, user.id, data.target_type, uuid.UUID(data.target_id), data.reason)


from sqlalchemy import select, func


@router.get("/reviews")
async def list_reviews(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Review, _Profile).join(_Profile, _Profile.id == Review.user_id).order_by(Review.created_at.desc()).limit(20)
    )).all()
    avg = (await db.execute(select(func.avg(Review.rating)))).scalar()
    cnt = (await db.execute(select(func.count(Review.id)))).scalar()
    items = [{
        "rating": r.rating, "body": r.body,
        "name": p.display_name or p.username or "User",
        "avatar": p.avatar_url or f"https://i.pravatar.cc/150?u={p.id}",
        "at": r.created_at.isoformat() if r.created_at else None,
    } for r, p in rows]
    return {"average": round(float(avg), 1) if avg else 0, "count": int(cnt or 0), "items": items}


@router.post("/reviews")
async def submit_review(data: ReviewIn, user: _Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rating = max(1, min(5, data.rating))
    existing = (await db.execute(select(Review).where(Review.user_id == user.id))).scalar_one_or_none()
    if existing:
        existing.rating = rating
        existing.body = (data.body or "").strip() or None
    else:
        db.add(Review(user_id=user.id, rating=rating, body=(data.body or "").strip() or None))
    await db.commit()
    return {"ok": True}
