from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services import feature_service
from app.core.cache import cached

router = APIRouter()


@router.get("/features")
async def get_features(db: AsyncSession = Depends(get_db)):
    return await cached("features:all", 30, lambda: feature_service.get_flags(db))
