import base64
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, tuple_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anon import Actor
from app.models import Category, Content, ContentTag, Profile, Tag
from app.schemas.content import (
    CategoryIn,
    CategoryOut,
    ContentCardOut,
    ContentIn,
    Creator,
    TagIn,
    TagOut,
)

_PLACEHOLDER_THUMB = (
    "https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=1200"
)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "item"


def _unique_slug(base: str) -> str:
    return f"{slugify(base)}-{uuid.uuid4().hex[:6]}"


# ---------------- formatting helpers ----------------
def _fmt_views(n: int) -> str:
    def trim(x: float) -> str:
        return f"{x:.1f}".rstrip("0").rstrip(".")
    if n >= 1_000_000_000:
        return trim(n / 1_000_000_000) + "B"
    if n >= 1_000_000:
        return trim(n / 1_000_000) + "M"
    if n >= 1_000:
        return trim(n / 1_000) + "K"
    return str(n)


def _fmt_time_ago(dt: datetime | None) -> str:
    if not dt:
        return "just now"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = (now - dt).total_seconds()
    if secs < 3600:
        return f"{max(1, int(secs // 60))}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    if secs < 2592000:
        return f"{int(secs // 86400)}d"
    return f"{int(secs // 2592000)}mo"


def _fmt_duration(seconds: int | None) -> str | None:
    if not seconds:
        return None
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def to_card(c: Content) -> ContentCardOut:
    owner = c.owner
    verified = bool(owner and owner.role and owner.role.name in ("creator", "admin"))
    tier = "gems" if c.is_premium and c.price_gems else "free"
    return ContentCardOut(
        id=str(c.id),
        title=c.title,
        thumbnail=c.thumbnail_url or _PLACEHOLDER_THUMB,
        is_video=c.content_type == "video",
        is_short=c.is_short,
        duration=_fmt_duration(c.duration_seconds),
        creator=Creator(
            name=(owner.display_name or owner.username or "Creator") if owner else "Creator",
            avatar=(owner.avatar_url if owner and owner.avatar_url else
                    f"https://i.pravatar.cc/150?u={c.owner_id}"),
            verified=verified,
        ),
        tier=tier,
        price_gems=c.price_gems if tier == "gems" else None,
        views=_fmt_views(c.views),
        time_ago=_fmt_time_ago(c.published_at),
    )


# ---------------- feed ----------------
def _encode_cursor(dt: datetime, cid: uuid.UUID) -> str:
    raw = f"{dt.isoformat()}|{cid}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        dt_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(dt_str), uuid.UUID(id_str)
    except Exception:
        return None


async def list_feed(
    db: AsyncSession,
    limit: int,
    cursor: str | None,
    category_slug: str | None = None,
) -> tuple[list[ContentCardOut], str | None]:
    stmt = (
        select(Content)
        .where(Content.status == "published", Content.visibility == "public",
               Content.is_short.is_(False))
        .order_by(Content.published_at.desc(), Content.id.desc())
        .limit(limit + 1)
    )

    if category_slug and category_slug not in ("All Universe", ""):
        cat = await db.execute(select(Category.id).where(Category.slug == category_slug))
        cat_id = cat.scalar_one_or_none()
        if cat_id is not None:
            stmt = stmt.where(Content.category_id == cat_id)

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            pub, cid = decoded
            stmt = stmt.where(
                tuple_(Content.published_at, Content.id) < (pub, cid)
            )

    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        if last.published_at:
            next_cursor = _encode_cursor(last.published_at, last.id)

    cards = [to_card(c) for c in rows]
    try:
        from app.services import monetization_service as _mon
        vmap = await _mon.active_vip_map(db, [c.owner_id for c in rows])
        for card, c in zip(cards, rows):
            card.creator.vip_tier = vmap.get(c.owner_id)
    except Exception:
        pass
    return cards, next_cursor


# ---------------- content create ----------------
async def _get_or_create_tags(db: AsyncSession, names: list[str]) -> list[Tag]:
    out: list[Tag] = []
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        slug = slugify(name)
        existing = await db.execute(select(Tag).where(Tag.slug == slug))
        tag = existing.scalar_one_or_none()
        if not tag:
            tag = Tag(name=name, slug=slug, status="active")
            db.add(tag)
            await db.flush()
        out.append(tag)
    return out


async def create_content(
    db: AsyncSession, owner_id: uuid.UUID, data: ContentIn
) -> Content:
    content = Content(
        owner_id=owner_id,
        title=data.title,
        slug=_unique_slug(data.title),
        description=data.description,
        content_type=data.content_type,
        is_short=data.is_short,
        category_id=uuid.UUID(data.category_id) if data.category_id else None,
        thumbnail_url=data.thumbnail_url,
        media_url=data.media_url,
        source="external",
        duration_seconds=data.duration_seconds,
        visibility=data.visibility,
        status="published",
        is_premium=data.is_premium,
        price_gems=data.price_gems if data.is_premium else None,
        allow_comments=data.allow_comments,
        published_at=datetime.now(timezone.utc),
    )
    db.add(content)
    await db.flush()

    for tag in await _get_or_create_tags(db, data.tags):
        db.add(ContentTag(content_id=content.id, tag_id=tag.id))

    await db.commit()
    reloaded = await db.execute(select(Content).where(Content.id == content.id))
    return reloaded.scalar_one()


async def list_by_owner(
    db: AsyncSession, owner_id: uuid.UUID, limit: int = 50
) -> list[Content]:
    res = await db.execute(
        select(Content)
        .where(Content.owner_id == owner_id)
        .order_by(Content.created_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


# ---------------- categories ----------------
def category_out(c: Category) -> CategoryOut:
    return CategoryOut(
        id=str(c.id),
        parent_id=str(c.parent_id) if c.parent_id else None,
        name=c.name,
        slug=c.slug,
        description=c.description,
        thumbnail_url=c.thumbnail_url,
        position=c.position,
        is_active=c.is_active,
    )


async def list_categories(db: AsyncSession, active_only: bool = True) -> list[Category]:
    stmt = select(Category).order_by(Category.position, Category.name)
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def create_category(db: AsyncSession, data: CategoryIn) -> Category:
    cat = Category(
        name=data.name,
        slug=_unique_slug(data.name),
        parent_id=uuid.UUID(data.parent_id) if data.parent_id else None,
        description=data.description,
        thumbnail_url=data.thumbnail_url,
        cover_url=data.cover_url,
        position=data.position,
        is_active=data.is_active,
    )
    db.add(cat)
    await db.commit()
    return cat


# ---------------- tags ----------------
def tag_out(t: Tag) -> TagOut:
    return TagOut(id=str(t.id), name=t.name, slug=t.slug, status=t.status)


async def list_tags(db: AsyncSession, active_only: bool = True) -> list[Tag]:
    stmt = select(Tag).order_by(Tag.name)
    if active_only:
        stmt = stmt.where(Tag.status == "active")
    return list((await db.execute(stmt)).scalars().all())


async def create_tag(db: AsyncSession, data: TagIn) -> Tag:
    tag = Tag(name=data.name, slug=_unique_slug(data.name), status=data.status)
    db.add(tag)
    await db.commit()
    return tag


async def get_detail(db: AsyncSession, content_id: uuid.UUID, current_user_id: uuid.UUID | None = None, current_anon_id: str | None = None):
    from app.models import ContentTag as _CT
    from app.schemas.content import CategoryRef, ContentDetailOut

    res = await db.execute(select(Content).where(Content.id == content_id))
    c = res.scalar_one_or_none()
    if not c or c.status != "published":
        return None

    # (View count + watch history are recorded separately via POST /content/{id}/view
    #  so this read stays cheap and safe to prefetch/cache.)

    # Derived fields (individual queries — reliable). No rollback on error
    # (rollback would expire the loaded content object and break to_card()).
    tags: list[str] = []
    like_count = follower_count = comment_count = 0
    is_liked = is_disliked = is_following = is_saved = False
    try:
        from app.models import Comment, Dislike as _Dislike, Follow, Like, Save

        tres = await db.execute(select(Tag).join(_CT, _CT.tag_id == Tag.id).where(_CT.content_id == content_id))
        tags = [t.name for t in tres.scalars().all()]

        like_count = await _count(db, Like, content_id=content_id)
        follower_count = await _count(db, Follow, creator_id=c.owner_id)
        comment_count = await _count(db, Comment, content_id=content_id)

        if current_user_id or current_anon_id:
            like_w = (Like.user_id == current_user_id) if current_user_id else (Like.anon_id == current_anon_id)
            dis_w = (_Dislike.user_id == current_user_id) if current_user_id else (_Dislike.anon_id == current_anon_id)
            is_liked = (await db.execute(select(Like.content_id).where(Like.content_id == content_id, like_w))).first() is not None
            is_disliked = (await db.execute(select(_Dislike.content_id).where(_Dislike.content_id == content_id, dis_w))).first() is not None
        if current_user_id:
            is_following = (await db.execute(select(Follow.creator_id).where(Follow.follower_id == current_user_id, Follow.creator_id == c.owner_id))).first() is not None
            is_saved = (await db.execute(select(Save.content_id).where(Save.user_id == current_user_id, Save.content_id == content_id))).first() is not None
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("content").warning("get_detail derived fields failed: %s", exc)

    is_locked = False
    if c.is_premium and c.price_gems and c.owner_id != current_user_id:
        try:
            from app.services import monetization_service as _mon
            is_locked = not await _mon.is_unlocked(db, current_user_id, content_id)
        except Exception:
            is_locked = True

    card = to_card(c)
    return ContentDetailOut(
        id=str(c.id),
        title=c.title,
        description=c.description,
        content_type=c.content_type,
        media_url=None if is_locked else c.media_url,
        thumbnail_url=c.thumbnail_url,
        duration=_fmt_duration(c.duration_seconds),
        is_premium=c.is_premium,
        price_gems=c.price_gems if (c.is_premium and c.price_gems) else None,
        tier=card.tier,
        views=c.views,
        views_display=_fmt_views(c.views),
        time_ago=_fmt_time_ago(c.published_at),
        creator=card.creator,
        category=CategoryRef(name=c.category.name, slug=c.category.slug) if c.category else None,
        tags=tags,
        creator_id=str(c.owner_id),
        like_count=like_count,
        is_liked=is_liked,
        follower_count=follower_count,
        is_following=is_following,
        comment_count=comment_count,
        is_disliked=is_disliked,
        is_saved=is_saved,
        visibility=c.visibility,
        content_type_out=c.content_type,
        is_locked=is_locked,
    )


# ---------------- likes ----------------
def _actor_where(model, actor: Actor):
    if actor.user_id is not None:
        return model.user_id == actor.user_id
    return model.anon_id == actor.anon_id

async def _count(db: AsyncSession, model, **filters) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(model)
    for k, v in filters.items():
        stmt = stmt.where(getattr(model, k) == v)
    return int((await db.execute(stmt)).scalar_one())


async def toggle_like(
    db: AsyncSession, content_id: uuid.UUID, actor: Actor
) -> tuple[bool, int]:
    from app.models import Dislike, Like

    drow = (await db.execute(
        select(Dislike).where(Dislike.content_id == content_id, _actor_where(Dislike, actor))
    )).scalar_one_or_none()
    if drow:
        await db.delete(drow)

    row = (await db.execute(
        select(Like).where(Like.content_id == content_id, _actor_where(Like, actor))
    )).scalar_one_or_none()
    if row:
        await db.delete(row)
        liked = False
    else:
        db.add(Like(content_id=content_id, user_id=actor.user_id,
                    anon_id=None if actor.user_id else actor.anon_id))
        liked = True
    await db.commit()
    return liked, await _count(db, Like, content_id=content_id)


async def toggle_dislike(
    db: AsyncSession, content_id: uuid.UUID, actor: Actor
) -> tuple[bool, int]:
    from app.models import Dislike, Like

    lrow = (await db.execute(
        select(Like).where(Like.content_id == content_id, _actor_where(Like, actor))
    )).scalar_one_or_none()
    if lrow:
        await db.delete(lrow)

    row = (await db.execute(
        select(Dislike).where(Dislike.content_id == content_id, _actor_where(Dislike, actor))
    )).scalar_one_or_none()
    if row:
        await db.delete(row)
        disliked = False
    else:
        db.add(Dislike(content_id=content_id, user_id=actor.user_id,
                       anon_id=None if actor.user_id else actor.anon_id))
        disliked = True
    await db.commit()
    return disliked, await _count(db, Like, content_id=content_id)


async def list_by_owner_public(
    db: AsyncSession, owner_id: uuid.UUID, kind: str | None = None, limit: int = 60
):
    stmt = select(Content).where(
        Content.owner_id == owner_id,
        Content.status == "published",
        Content.visibility == "public",
    )
    if kind in ("short", "shorts", "reel", "reels"):
        stmt = stmt.where(Content.content_type == "video", Content.is_short.is_(True))
    elif kind in ("video", "videos"):
        stmt = stmt.where(Content.content_type == "video", Content.is_short.is_(False))
    elif kind in ("photo", "photos"):
        stmt = stmt.where(Content.content_type == "photo")
    stmt = stmt.order_by(Content.published_at.desc(), Content.id.desc()).limit(limit)
    res = await db.execute(stmt)
    return [to_card(c) for c in res.scalars().all()]


async def update_content(db: AsyncSession, content_id: uuid.UUID, user: Profile, data: dict):
    from app.models import ContentTag

    c = (await db.execute(select(Content).where(Content.id == content_id))).scalar_one_or_none()
    if not c:
        raise ValueError("Content not found")
    is_admin = bool(user.role and user.role.name == "admin")
    if not (c.owner_id == user.id or is_admin):
        raise PermissionError("Not allowed")

    for field in ("title", "description", "visibility", "status", "thumbnail_url", "is_premium", "price_gems", "content_type", "allow_comments", "allow_download", "is_short"):
        if field in data and data[field] is not None:
            setattr(c, field, data[field])
    if data.get("category_id") is not None:
        c.category_id = uuid.UUID(data["category_id"]) if data["category_id"] else None
    if not c.is_premium:
        c.price_gems = None

    if "tags" in data and data["tags"] is not None:
        await db.execute(ContentTag.__table__.delete().where(ContentTag.content_id == c.id))
        for tag in await _get_or_create_tags(db, data["tags"]):
            db.add(ContentTag(content_id=c.id, tag_id=tag.id))

    await db.commit()
    return c


async def delete_content(db: AsyncSession, content_id: uuid.UUID, user: Profile) -> None:
    c = (await db.execute(select(Content).where(Content.id == content_id))).scalar_one_or_none()
    if not c:
        raise ValueError("Content not found")
    is_admin = bool(user.role and user.role.name == "admin")
    if not (c.owner_id == user.id or is_admin):
        raise PermissionError("Not allowed")
    await db.delete(c)
    await db.commit()


async def toggle_save(db: AsyncSession, user_id: uuid.UUID, content_id: uuid.UUID) -> bool:
    from app.models import Save
    row = (await db.execute(
        select(Save).where(Save.user_id == user_id, Save.content_id == content_id)
    )).scalar_one_or_none()
    if row:
        await db.delete(row); saved = False
    else:
        db.add(Save(user_id=user_id, content_id=content_id)); saved = True
    await db.commit()
    return saved


async def list_saved(db: AsyncSession, user_id: uuid.UUID, limit: int = 60):
    from app.models import Save
    res = await db.execute(
        select(Content).join(Save, Save.content_id == Content.id)
        .where(Save.user_id == user_id)
        .order_by(Save.created_at.desc())
        .limit(limit)
    )
    return [to_card(c) for c in res.scalars().all()]


async def list_history(db: AsyncSession, user_id: uuid.UUID, limit: int = 60):
    from app.models import WatchHistory
    res = await db.execute(
        select(Content).join(WatchHistory, WatchHistory.content_id == Content.id)
        .where(WatchHistory.user_id == user_id)
        .order_by(WatchHistory.watched_at.desc())
        .limit(limit)
    )
    return [to_card(c) for c in res.scalars().all()]


async def list_liked(db: AsyncSession, user_id: uuid.UUID, limit: int = 60):
    from app.models import Like
    res = await db.execute(
        select(Content).join(Like, Like.content_id == Content.id)
        .where(Like.user_id == user_id)
        .order_by(Like.created_at.desc())
        .limit(limit)
    )
    return [to_card(c) for c in res.scalars().all()]


async def record_view(db: AsyncSession, content_id: uuid.UUID, user_id: uuid.UUID | None):
    """Increment view count + (for a user) upsert watch history — one round-trip."""
    from sqlalchemy import text as _text
    try:
        await db.execute(_text("update content set views = coalesce(views,0)+1 where id = cast(:cid as uuid)"),
                         {"cid": str(content_id)})
        if user_id:
            await db.execute(_text(
                "insert into watch_history (user_id, content_id, watched_at) "
                "values (cast(:u as uuid), cast(:c as uuid), now()) "
                "on conflict (user_id, content_id) do update set watched_at = now()"
            ), {"u": str(user_id), "c": str(content_id)})
        await db.commit()
    except Exception:
        await db.rollback()


async def reels_feed(db: AsyncSession, current_user_id, current_anon_id, cursor: str | None = None, limit: int = 6):
    import hashlib
    from app.models import Follow, Like
    offset = int(cursor) if (cursor and str(cursor).isdigit()) else 0

    rows = (await db.execute(text("""
        select c.id as id, extract(epoch from (now() - c.published_at)) / 3600.0 as age,
          coalesce(c.views, 0) as v,
          (select count(*) from likes    where content_id = c.id) as l,
          (select count(*) from comments where content_id = c.id) as cc
        from content c
        where c.is_short = true and c.status = 'published' and c.visibility = 'public'
        order by c.published_at desc limit 150
    """))).mappings().all()

    cnt = {r["id"]: (r["l"] or 0, r["cc"] or 0) for r in rows}
    vkey = str(current_user_id) if current_user_id else (current_anon_id or "anon")

    def _jit(b):
        h = hashlib.md5(f"{vkey}:{b}".encode()).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF

    def _score(v, l, cc, age):
        return (v * 0.15 + l * 2 + cc * 3 + 1) / ((max(age, 0.0) + 2.0) ** 1.5)

    ranked = sorted(
        ((_score(r["v"], r["l"], r["cc"], float(r["age"] or 0)) * (0.35 + _jit(r["id"]) * 1.3), r["id"]) for r in rows),
        key=lambda x: x[0], reverse=True,
    )
    page = ranked[offset:offset + limit]
    has_more = len(ranked) > offset + limit
    ids = [pid for _, pid in page]
    if not ids:
        return [], None

    contents = {c.id: c for c in (await db.execute(select(Content).where(Content.id.in_(ids)))).scalars().all()}
    liked = following = set()
    owners = list({contents[i].owner_id for i in ids if i in contents})
    if current_user_id and ids:
        liked = set((await db.execute(select(Like.content_id).where(Like.user_id == current_user_id, Like.content_id.in_(ids)))).scalars().all())
        following = set((await db.execute(select(Follow.creator_id).where(Follow.follower_id == current_user_id, Follow.creator_id.in_(owners)))).scalars().all())
    try:
        from app.services import monetization_service as _mon
        vmap = await _mon.active_vip_map(db, owners)
    except Exception:
        vmap = {}

    items = []
    for _, pid in page:
        c = contents.get(pid)
        if not c:
            continue
        lc, ccnt = cnt.get(pid, (0, 0))
        locked = False
        if c.is_premium and c.price_gems and c.owner_id != current_user_id:
            try:
                from app.services import monetization_service as _mon
                locked = not await _mon.is_unlocked(db, current_user_id, c.id)
            except Exception:
                locked = True
        card = to_card(c)
        items.append({
            "id": str(c.id), "title": c.title, "content_type": c.content_type,
            "media_url": None if locked else c.media_url, "thumbnail_url": c.thumbnail_url,
            "is_premium": c.is_premium, "price_gems": c.price_gems if (c.is_premium and c.price_gems) else None,
            "is_locked": locked, "creator": {**card.creator.model_dump(), "vip_tier": vmap.get(c.owner_id)}, "creator_id": str(c.owner_id),
            "like_count": lc, "comment_count": ccnt,
            "is_liked": (c.id in liked), "is_following": (c.owner_id in following),
        })
    return items, (str(offset + limit) if has_more else None)


async def top_thumb_for_category(db: AsyncSession, category_id) -> str | None:
    row = (await db.execute(text("""
        select c.thumbnail_url from content c
        where c.category_id = cast(:cat as uuid) and c.status='published' and c.visibility='public'
              and c.thumbnail_url is not null
        order by (coalesce(c.views,0)*0.1
                  + (select count(*) from likes where content_id=c.id)*2
                  + (select count(*) from comments where content_id=c.id)*3) desc
        limit 1
    """), {"cat": str(category_id)})).scalar_one_or_none()
    return row


async def list_manage(db: AsyncSession, owner_id: uuid.UUID, limit: int = 200):
    from app.models import Comment, Like
    rows = (await db.execute(
        select(Content).where(Content.owner_id == owner_id).order_by(Content.created_at.desc()).limit(limit)
    )).scalars().all()
    out = []
    for c in rows:
        lc = await _count(db, Like, content_id=c.id)
        cc = await _count(db, Comment, content_id=c.id)
        out.append({
            "id": str(c.id), "title": c.title, "thumbnail_url": c.thumbnail_url,
            "content_type": c.content_type, "is_short": c.is_short,
            "status": c.status, "visibility": c.visibility,
            "is_premium": c.is_premium, "price_gems": c.price_gems,
            "allow_comments": c.allow_comments, "allow_download": c.allow_download,
            "category_id": str(c.category_id) if c.category_id else None,
            "views": c.views or 0, "like_count": lc, "comment_count": cc,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return out


async def trending_feed(db: AsyncSession, limit: int = 30):
    """Rank recent public content by engagement + recency (views, likes, comments)."""
    rows = (await db.execute(text("""
        select c.id as id,
          coalesce(c.views,0) as v,
          (select count(*) from likes where content_id=c.id) as l,
          (select count(*) from comments where content_id=c.id) as cc,
          extract(epoch from (now() - coalesce(c.published_at, c.created_at))) / 3600.0 as age
        from content c
        where c.status='published' and c.visibility='public' and c.is_short = false
        order by c.published_at desc nulls last limit 300
    """))).mappings().all()
    def score(v, l, cc, age):
        return (v * 0.2 + l * 4 + cc * 6 + 1) / ((max(age, 0.0) + 4.0) ** 0.6)
    ranked = sorted(((score(r["v"], r["l"], r["cc"], float(r["age"] or 0)), r["id"]) for r in rows),
                    key=lambda x: x[0], reverse=True)[:limit]
    ids = [pid for _, pid in ranked]
    if not ids:
        return []
    found = {c.id: c for c in (await db.execute(select(Content).where(Content.id.in_(ids)))).scalars().all()}
    cards = [to_card(found[i]) for i in ids if i in found]
    try:
        from app.services import monetization_service as _mon
        vmap = await _mon.active_vip_map(db, [found[i].owner_id for i in ids if i in found])
        for card, i in zip(cards, [i for i in ids if i in found]):
            card.creator.vip_tier = vmap.get(found[i].owner_id)
    except Exception:
        pass
    return cards
