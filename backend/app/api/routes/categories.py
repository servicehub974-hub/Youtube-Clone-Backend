from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.db import get_db
from app.models import Profile
from app.schemas.content import CategoryIn, CategoryOut
from app.services import content_service
from app.core.cache import cached, invalidate

router = APIRouter(prefix="/categories")


@router.get("", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    async def build():
        cats = await content_service.list_categories(db, active_only=True)
        return [content_service.category_out(c) for c in cats]

    return await cached("categories:list", 60, build)


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    data: CategoryIn,
    _admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cat = await content_service.create_category(db, data)
    invalidate("categories:")
    return content_service.category_out(cat)
