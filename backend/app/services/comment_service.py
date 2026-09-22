import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anon import Actor
from app.models import Comment, CommentLike, Content
from app.schemas.comment import CommentAuthor, CommentOut
from app.services.content_service import _fmt_time_ago
from app.services import notification_service


class CommentError(Exception):
    pass


def _actor_name(actor: Actor) -> str:
    if actor.user_id and actor.user:
        return getattr(actor.user, "display_name", None) or getattr(actor.user, "username", None) or "Someone"
    return "A guest"


def _actor_avatar(actor: Actor) -> str:
    if actor.user_id and actor.user and getattr(actor.user, "avatar_url", None):
        return actor.user.avatar_url
    seed = (actor.anon_id or str(actor.user_id) or "g")[:8]
    return f"https://i.pravatar.cc/150?u={seed}"


def _actor_where(model, actor: Actor):
    if actor.user_id is not None:
        return model.user_id == actor.user_id
    return model.anon_id == actor.anon_id


def _author(c: Comment, vip_map: dict | None = None) -> CommentAuthor:
    if c.user_id and c.author:
        p = c.author
        return CommentAuthor(
            id=str(p.id),
            name=p.display_name or p.username or "User",
            avatar=p.avatar_url or f"https://i.pravatar.cc/150?u={p.id}",
            verified=bool(p.role and p.role.name in ("creator", "admin")),
            vip_tier=(vip_map or {}).get(c.user_id),
        )
    seed = (c.anon_id or "guest")[:8]
    return CommentAuthor(
        id="",
        name=c.anon_name or "Anonymous",
        avatar=f"https://i.pravatar.cc/150?u=guest-{seed}",
        verified=False,
    )


async def _like_map(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    res = await db.execute(
        select(CommentLike.comment_id, func.count())
        .where(CommentLike.comment_id.in_(ids))
        .group_by(CommentLike.comment_id)
    )
    return {row[0]: int(row[1]) for row in res.all()}


async def _reply_map(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    res = await db.execute(
        select(Comment.parent_id, func.count())
        .where(Comment.parent_id.in_(ids))
        .group_by(Comment.parent_id)
    )
    return {row[0]: int(row[1]) for row in res.all()}


async def _liked_set(db: AsyncSession, ids: list[uuid.UUID], actor: Actor | None) -> set[uuid.UUID]:
    if not ids or actor is None or (actor.user_id is None and actor.anon_id is None):
        return set()
    res = await db.execute(
        select(CommentLike.comment_id).where(
            CommentLike.comment_id.in_(ids), _actor_where(CommentLike, actor)
        )
    )
    return {row[0] for row in res.all()}


def _out(c: Comment, likes: int, liked: bool, replies: int, vip_map: dict | None = None) -> CommentOut:
    return CommentOut(
        id=str(c.id),
        parent_id=str(c.parent_id) if c.parent_id else None,
        body=c.body,
        time_ago=_fmt_time_ago(c.created_at),
        author=_author(c, vip_map),
        like_count=likes,
        is_liked=liked,
        reply_count=replies,
        is_pinned=c.is_pinned,
    )


async def count_for_content(db: AsyncSession, content_id: uuid.UUID) -> int:
    res = await db.execute(
        select(func.count()).select_from(Comment).where(Comment.content_id == content_id)
    )
    return int(res.scalar_one())


async def list_comments(
    db: AsyncSession, content_id: uuid.UUID, actor: Actor | None, sort: str = "top"
) -> list[CommentOut]:
    rows = list((await db.execute(
        select(Comment).where(Comment.content_id == content_id, Comment.parent_id.is_(None))
    )).scalars().all())
    ids = [c.id for c in rows]
    likes = await _like_map(db, ids)
    replies = await _reply_map(db, ids)
    liked = await _liked_set(db, ids, actor)

    def key(c: Comment):
        return (c.is_pinned, likes.get(c.id, 0) if sort == "top" else c.created_at)

    rows.sort(key=key, reverse=True)
    from app.services import monetization_service as _mon
    vmap = await _mon.active_vip_map(db, [c.user_id for c in rows if c.user_id])
    return [_out(c, likes.get(c.id, 0), c.id in liked, replies.get(c.id, 0), vmap) for c in rows]


async def list_replies(
    db: AsyncSession, parent_id: uuid.UUID, actor: Actor | None
) -> list[CommentOut]:
    rows = list((await db.execute(
        select(Comment).where(Comment.parent_id == parent_id).order_by(Comment.created_at.asc())
    )).scalars().all())
    ids = [c.id for c in rows]
    likes = await _like_map(db, ids)
    liked = await _liked_set(db, ids, actor)
    from app.services import monetization_service as _mon
    vmap = await _mon.active_vip_map(db, [c.user_id for c in rows if c.user_id])
    return [_out(c, likes.get(c.id, 0), c.id in liked, 0, vmap) for c in rows]


async def create_comment(
    db: AsyncSession,
    content_id: uuid.UUID,
    actor: Actor,
    body: str,
    parent_id: uuid.UUID | None,
    anon_name: str | None = None,
) -> CommentOut:
    parent = None
    if parent_id:
        parent = (await db.execute(select(Comment).where(Comment.id == parent_id))).scalar_one_or_none()
        if not parent:
            raise CommentError("Parent comment not found.")
        if parent.parent_id is not None:
            parent_id = parent.parent_id

    c = Comment(
        content_id=content_id,
        user_id=actor.user_id,
        anon_id=None if actor.user_id else actor.anon_id,
        anon_name=None if actor.user_id else ((anon_name or "").strip()[:40] or "Anonymous"),
        body=body.strip(),
        parent_id=parent_id,
    )
    db.add(c)
    try:
        name = _actor_name(actor)
        link = f"/content/{content_id}"
        trow = (await db.execute(select(Content.owner_id, Content.thumbnail_url, Content.title).where(Content.id == content_id))).first()
        thumb = trow[1] if trow else None
        ctitle = trow[2] if trow else ""
        av = _actor_avatar(actor)
        if parent is not None:
            if parent.user_id and parent.user_id != actor.user_id:
                notification_service.add(db, parent.user_id, "reply", name, "replied to your comment", link, thumb, av)
        else:
            owner = trow[0] if trow else None
            if owner and owner != actor.user_id:
                msg = f'commented on "{ctitle}"' if ctitle else "commented on your content"
                notification_service.add(db, owner, "comment", name, msg, link, thumb, av)
    except Exception:
        pass
    await db.commit()
    reloaded = (await db.execute(select(Comment).where(Comment.id == c.id))).scalar_one()
    return _out(reloaded, 0, False, 0)


async def toggle_comment_like(db: AsyncSession, comment_id: uuid.UUID, actor: Actor) -> tuple[bool, int]:
    existing = (await db.execute(
        select(CommentLike).where(CommentLike.comment_id == comment_id, _actor_where(CommentLike, actor))
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        liked = False
    else:
        db.add(CommentLike(comment_id=comment_id, user_id=actor.user_id,
                           anon_id=None if actor.user_id else actor.anon_id))
        liked = True
    if liked:
        try:
            c = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
            if c and c.user_id and c.user_id != actor.user_id:
                _thumb = (await db.execute(select(Content.thumbnail_url).where(Content.id == c.content_id))).scalar_one_or_none()
                notification_service.add(db, c.user_id, "comment_like", _actor_name(actor), "liked your comment", f"/content/{c.content_id}", _thumb, _actor_avatar(actor))
        except Exception:
            pass
    await db.commit()
    cnt = await db.execute(
        select(func.count()).select_from(CommentLike).where(CommentLike.comment_id == comment_id)
    )
    return liked, int(cnt.scalar_one())


async def _content_owner(db: AsyncSession, content_id: uuid.UUID) -> uuid.UUID | None:
    res = await db.execute(select(Content.owner_id).where(Content.id == content_id))
    return res.scalar_one_or_none()


async def delete_comment(db: AsyncSession, comment_id: uuid.UUID, actor: Actor) -> None:
    c = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise CommentError("Comment not found.")
    if actor.user_id is not None:
        owner = await _content_owner(db, c.content_id)
        allowed = c.user_id == actor.user_id or owner == actor.user_id or actor.role_name == "admin"
    else:
        allowed = c.anon_id is not None and c.anon_id == actor.anon_id
    if not allowed:
        raise CommentError("Not allowed.")
    await db.delete(c)
    await db.commit()


async def toggle_pin(db: AsyncSession, comment_id: uuid.UUID, actor: Actor) -> bool:
    if actor.user_id is None:
        raise CommentError("Only the content owner can pin.")
    c = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise CommentError("Comment not found.")
    owner = await _content_owner(db, c.content_id)
    if not (owner == actor.user_id or actor.role_name == "admin"):
        raise CommentError("Only the content owner can pin.")
    c.is_pinned = not c.is_pinned
    await db.commit()
    return c.is_pinned
