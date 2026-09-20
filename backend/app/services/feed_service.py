"""Mixed ranked feed: posts + videos, blended by engagement + recency.

Hot score = (engagement + 1) / (age_hours + 2)^1.5 — surfaces popular content
while keeping fresh items visible (so a refresh brings new posts up).
"""
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Content
from app.services import post_service
from app.services.content_service import to_card


def _score(engagement: float, age_hours: float) -> float:
    return (engagement + 1.0) / ((max(age_hours, 0.0) + 2.0) ** 1.5)


async def mixed_feed(db: AsyncSession, viewer_id: uuid.UUID | None, offset: int = 0, limit: int = 8):
    prows = (await db.execute(text("""
        select p.id as id,
          extract(epoch from (now() - p.created_at)) / 3600.0 as age,
          (select count(*) from post_likes    where post_id = p.id) as l,
          (select count(*) from post_comments where post_id = p.id) as c,
          (select count(*) from posts r where r.repost_of = p.id)   as r
        from posts p order by p.created_at desc limit 150
    """))).mappings().all()

    vrows = (await db.execute(text("""
        select c.id as id,
          extract(epoch from (now() - c.published_at)) / 3600.0 as age,
          coalesce(c.views, 0) as v,
          (select count(*) from likes    where content_id = c.id) as l,
          (select count(*) from comments where content_id = c.id) as c2
        from content c
        where c.status = 'published' and c.visibility = 'public'
        order by c.published_at desc limit 150
    """))).mappings().all()

    cand: list[tuple[float, str, uuid.UUID]] = []
    for p in prows:
        eng = (p["l"] or 0) * 2 + (p["c"] or 0) * 3 + (p["r"] or 0) * 2
        cand.append((_score(eng, float(p["age"] or 0)), "post", p["id"]))
    for v in vrows:
        eng = float(v["v"] or 0) * 0.15 + (v["l"] or 0) * 2 + (v["c2"] or 0) * 3
        cand.append((_score(eng, float(v["age"] or 0)), "video", v["id"]))

    cand.sort(key=lambda x: x[0], reverse=True)
    page = cand[offset:offset + limit]
    has_more = len(cand) > offset + limit

    items = []
    for _, kind, cid in page:
        if kind == "post":
            po = await post_service.get(db, cid, viewer_id)
            if po:
                items.append({"type": "post", "post": po.model_dump()})
        else:
            c = (await db.execute(select(Content).where(Content.id == cid))).scalar_one_or_none()
            if c:
                items.append({"type": "video", "video": to_card(c).model_dump()})

    return items, (offset + limit if has_more else None)
