import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, require_admin
from app.core.db import get_db
from app.models import Feedback, Profile

router = APIRouter()


class FeedbackIn(BaseModel):
    category: str | None = None
    message: str = Field(min_length=2, max_length=4000)
    name: str | None = None
    email: str | None = None


@router.post("/feedback")
async def submit_feedback(data: FeedbackIn, user: Profile | None = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
    fb = Feedback(
        user_id=user.id if user else None,
        name=(data.name or (user.display_name or user.username if user else None)),
        email=data.email, category=data.category, message=data.message.strip(),
    )
    db.add(fb)
    await db.commit()
    return {"ok": True}


@router.get("/admin/feedback")
async def list_feedback(admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Feedback).order_by(Feedback.created_at.desc()).limit(200))).scalars().all()
    return [
        {"id": str(f.id), "name": f.name or "Anonymous", "email": f.email,
         "category": f.category, "message": f.message,
         "created_at": f.created_at.isoformat() if f.created_at else None}
        for f in rows
    ]
