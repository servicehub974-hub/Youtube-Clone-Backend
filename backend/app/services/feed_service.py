"""Posts feed — ranked by engagement + recency, with a per-user shuffle so
different users see a different order (and a refresh surfaces newer posts)."""
import hashlib
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import post_service


def _score(engagement: float, age_hours: float) -> float:
    return (engagement + 1.0) / ((max(age_hours, 0.0) + 2.0) ** 1.5)


def _jitter(a: str, b) -> float:
    h = hashlib.md5(f"{a}:{b}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF  # 0..1


async def posts_feed(db: AsyncSession, viewer_id: uuid.UUID | None, offset: int = 0, limit: int = 8):
    rows = (await db.execute(text("""
        select p.id as id,
          extract(epoch from (now() - p.created_at)) / 3600.0 as age,
          (select count(*) from post_likes    where post_id = p.id) as l,
          (select count(*) from post_comments where post_id = p.id) as c,
          (select count(*) from posts r where r.repost_of = p.id)   as r
        from posts p order by p.created_at desc limit 200
    """))).mappings().all()

    vkey = str(viewer_id) if viewer_id else "anon"
    ranked: list[tuple[float, uuid.UUID]] = []
    for p in rows:
        eng = (p["l"] or 0) * 2 + (p["c"] or 0) * 3 + (p["r"] or 0) * 2
        base = _score(eng, float(p["age"] or 0))
        ranked.append((base * (0.7 + _jitter(vkey, p["id"]) * 0.6), p["id"]))

    ranked.sort(key=lambda x: x[0], reverse=True)
    page = ranked[offset:offset + limit]
    has_more = len(ranked) > offset + limit

    items = []
    for _, pid in page:
        po = await post_service.get(db, pid, viewer_id)
        if po:
            items.append(po.model_dump())
    return items, (offset + limit if has_more else None)
