"""Posts feed — ranked by engagement + recency, per-user shuffle, batched
(no N+1) so it loads as fast as the video feed."""
import hashlib
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Follow, Post, PostComment, PostLike, PostSave
from app.services import post_service
from app.services.content_service import _count


def _score(engagement: float, age_hours: float) -> float:
    return (engagement + 1.0) / ((max(age_hours, 0.0) + 2.0) ** 1.5)


def _jitter(a: str, b) -> float:
    h = hashlib.md5(f"{a}:{b}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


async def posts_feed(db: AsyncSession, viewer_id: uuid.UUID | None, offset: int = 0, limit: int = 8):
    rows = (await db.execute(text("""
        select p.id as id,
          extract(epoch from (now() - p.created_at)) / 3600.0 as age,
          (select count(*) from post_likes    where post_id = p.id) as l,
          (select count(*) from post_comments where post_id = p.id) as c,
          (select count(*) from posts r where r.repost_of = p.id)   as r
        from posts p order by p.created_at desc limit 200
    """))).mappings().all()

    cnt = {r["id"]: (r["l"] or 0, r["c"] or 0, r["r"] or 0) for r in rows}
    vkey = str(viewer_id) if viewer_id else "anon"
    ranked = sorted(
        ((_score((r["l"] or 0) * 2 + (r["c"] or 0) * 3 + (r["r"] or 0) * 2, float(r["age"] or 0)) * (0.7 + _jitter(vkey, r["id"]) * 0.6), r["id"]) for r in rows),
        key=lambda x: x[0], reverse=True,
    )
    page = ranked[offset:offset + limit]
    has_more = len(ranked) > offset + limit
    ids = [pid for _, pid in page]
    if not ids:
        return [], None

    posts = (await db.execute(select(Post).where(Post.id.in_(ids)))).scalars().all()
    by_id = {p.id: p for p in posts}
    ordered = [by_id[i] for i in ids if i in by_id]

    liked: set = set()
    saved: set = set()
    following: set = set()
    if viewer_id and ordered:
        liked = set((await db.execute(select(PostLike.post_id).where(PostLike.user_id == viewer_id, PostLike.post_id.in_(ids)))).scalars().all())
        saved = set((await db.execute(select(PostSave.post_id).where(PostSave.user_id == viewer_id, PostSave.post_id.in_(ids)))).scalars().all())
        author_ids = list({p.author_id for p in ordered})
        following = set((await db.execute(select(Follow.creator_id).where(Follow.follower_id == viewer_id, Follow.creator_id.in_(author_ids)))).scalars().all())

    # embedded repost originals (load once)
    orig_ids = list({p.repost_of for p in ordered if p.repost_of})
    orig_out = {}
    if orig_ids:
        for o in (await db.execute(select(Post).where(Post.id.in_(orig_ids)))).scalars().all():
            oc = cnt.get(o.id) or (await _count(db, PostLike, post_id=o.id), await _count(db, PostComment, post_id=o.id), 0)
            orig_out[o.id] = post_service.out_from(o, viewer_id, oc[0], oc[1], oc[2], o.id in liked, o.id in saved, o.author_id in following, None)

    try:
        from app.services import monetization_service as _mon
        vipmap = await _mon.active_vip_map(db, [p.author_id for p in ordered])
    except Exception:
        vipmap = {}

    items = []
    for p in ordered:
        lc, cc, rc = cnt.get(p.id, (0, 0, 0))
        original = orig_out.get(p.repost_of) if p.repost_of else None
        items.append(post_service.out_from(p, viewer_id, lc, cc, rc, p.id in liked, p.id in saved, p.author_id in following, original, vipmap.get(p.author_id)).model_dump())
    return items, (offset + limit if has_more else None)
