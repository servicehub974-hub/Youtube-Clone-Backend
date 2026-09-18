import base64
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, tuple_
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
        .where(Content.status == "published", Content.visibility == "public")
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

    return [to_card(c) for c in rows], next_cursor


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

    # All derived fields in ONE round-trip (big latency win for a remote DB).
    tags: list[str] = []
    like_count = follower_count = comment_count = 0
    is_liked = is_disliked = is_following = is_saved = False
    try:
        from sqlalchemy import text as _text

        row = (await db.execute(_text("""
            select
              (select count(*) from likes    where content_id = :cid::uuid) as like_count,
              (select count(*) from comments where content_id = :cid::uuid) as comment_count,
              (select count(*) from follows  where creator_id = :owner::uuid) as follower_count,
              coalesce((select array_agg(t.name) from content_tags ct join tags t on t.id = ct.tag_id
                        where ct.content_id = :cid::uuid), array[]::text[]) as tags,
              (case when :uid::uuid is not null then exists(select 1 from likes where content_id=:cid::uuid and user_id=:uid::uuid)
                    when :anon::text is not null then exists(select 1 from likes where content_id=:cid::uuid and anon_id=:anon::text)
                    else false end) as is_liked,
              (case when :uid::uuid is not null then exists(select 1 from dislikes where content_id=:cid::uuid and user_id=:uid::uuid)
                    when :anon::text is not null then exists(select 1 from dislikes where content_id=:cid::uuid and anon_id=:anon::text)
                    else false end) as is_disliked,
              (case when :uid::uuid is not null then exists(select 1 from follows where follower_id=:uid::uuid and creator_id=:owner::uuid) else false end) as is_following,
              (case when :uid::uuid is not null then exists(select 1 from saves where user_id=:uid::uuid and content_id=:cid::uuid) else false end) as is_saved
        """), {
            "cid": str(content_id),
            "owner": str(c.owner_id),
            "uid": str(current_user_id) if current_user_id else None,
            "anon": current_anon_id,
        })).mappings().one()
        like_count = int(row["like_count"])
        comment_count = int(row["comment_count"])
        follower_count = int(row["follower_count"])
        tags = list(row["tags"] or [])
        is_liked = bool(row["is_liked"])
        is_disliked = bool(row["is_disliked"])
        is_following = bool(row["is_following"])
        is_saved = bool(row["is_saved"])
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("content").warning("get_detail derived fields failed: %s", exc)
        # NOTE: do NOT rollback here — it would expire the already-loaded content
        # object and break to_card() below. Defaults above are fine.

    card = to_card(c)
    return ContentDetailOut(
        id=str(c.id),
        title=c.title,
        description=c.description,
        content_type=c.content_type,
        media_url=c.media_url,
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
    if kind == "short":
        stmt = stmt.where(Content.content_type == "video", Content.is_short.is_(True))
    elif kind == "video":
        stmt = stmt.where(Content.content_type == "video", Content.is_short.is_(False))
    elif kind == "photo":
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

    for field in ("title", "description", "visibility", "thumbnail_url", "is_premium", "price_gems", "content_type"):
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
        await db.execute(_text("update content set views = coalesce(views,0)+1 where id = :cid::uuid"),
                         {"cid": str(content_id)})
        if user_id:
            await db.execute(_text(
                "insert into watch_history (user_id, content_id, watched_at) "
                "values (:u::uuid, :c::uuid, now()) "
                "on conflict (user_id, content_id) do update set watched_at = now()"
            ), {"u": str(user_id), "c": str(content_id)})
        await db.commit()
    except Exception:
        await db.rollback()
