from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FeatureFlag

# Defaults when a flag row doesn't exist yet.
DEFAULTS = {"messages": True}


async def get_flags(db: AsyncSession) -> dict[str, bool]:
    rows = (await db.execute(select(FeatureFlag))).scalars().all()
    flags = dict(DEFAULTS)
    for r in rows:
        flags[r.key] = r.enabled
    return flags


async def is_enabled(db: AsyncSession, key: str) -> bool:
    row = (
        await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    if row is None:
        return DEFAULTS.get(key, True)
    return row.enabled


async def set_flag(db: AsyncSession, key: str, enabled: bool) -> bool:
    row = (
        await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    if row is None:
        row = FeatureFlag(key=key, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled
    await db.commit()
    return enabled
