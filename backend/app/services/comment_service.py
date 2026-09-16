import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment, CommentLike, Content, Profile
from app.schemas.comment import CommentAuthor, CommentOut
from app.services.content_service import _fmt_time_ago


class CommentError(Exception):
    pass


def _author(p: Profile | None, uid: uuid.UUID) -> CommentAuthor:
    if not p:
        return CommentAuthor(id=str(uid), name="User", avatar=f"https://i.pravatar.cc/150?u={uid}", verified=False)
    return CommentAuthor(
        id=str(p.id),
        name=p.display_name or p.username or "User",
        avatar=p.avatar_url or f"https://i.pravatar.cc/150?u={p.id}",
        verified=bool(p.role and p.role.name in ("creator", "admin")),
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


async def _liked_set(
    db: AsyncSession, ids: list[uuid.UUID], user_id: uuid.UUID | None
) -> set[uuid.UUID]:
    if not ids or not user_id:
        return set()
    res = await db.execute(
        select(CommentLike.comment_id).where(
            CommentLike.comment_id.in_(ids), CommentLike.user_id == user_id
        )
    )
    return {row[0] for row in res.all()}


def _out(c: Comment, likes: int, liked: bool, replies: int) -> CommentOut:
    return CommentOut(
        id=str(c.id),
        parent_id=str(c.parent_id) if c.parent_id else None,
        body=c.body,
        time_ago=_fmt_time_ago(c.created_at),
        author=_author(c.author, c.user_id),
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
    db: AsyncSession,
    content_id: uuid.UUID,
    current_user_id: uuid.UUID | None,
    sort: str = "top",
) -> list[CommentOut]:
    stmt = select(Comment).where(
        Comment.content_id == content_id, Comment.parent_id.is_(None)
    )
    rows = list((await db.execute(stmt)).scalars().all())

    ids = [c.id for c in rows]
    likes = await _like_map(db, ids)
    replies = await _reply_map(db, ids)
    liked = await _liked_set(db, ids, current_user_id)

    def sort_key(c: Comment):
        return (c.is_pinned, likes.get(c.id, 0) if sort == "top" else c.created_at)

    rows.sort(key=sort_key, reverse=True)
    return [_out(c, likes.get(c.id, 0), c.id in liked, replies.get(c.id, 0)) for c in rows]


async def list_replies(
    db: AsyncSession, parent_id: uuid.UUID, current_user_id: uuid.UUID | None
) -> list[CommentOut]:
    rows = list(
        (
            await db.execute(
                select(Comment)
                .where(Comment.parent_id == parent_id)
                .order_by(Comment.created_at.asc())
            )
        ).scalars().all()
    )
    ids = [c.id for c in rows]
    likes = await _like_map(db, ids)
    liked = await _liked_set(db, ids, current_user_id)
    return [_out(c, likes.get(c.id, 0), c.id in liked, 0) for c in rows]


async def create_comment(
    db: AsyncSession,
    content_id: uuid.UUID,
    user_id: uuid.UUID,
    body: str,
    parent_id: uuid.UUID | None,
) -> CommentOut:
    if parent_id:
        parent = (
            await db.execute(select(Comment).where(Comment.id == parent_id))
        ).scalar_one_or_none()
        if not parent:
            raise CommentError("Parent comment not found.")
        # enforce max 2 levels: replies attach to the top-level parent
        if parent.parent_id is not None:
            parent_id = parent.parent_id

    c = Comment(content_id=content_id, user_id=user_id, body=body.strip(), parent_id=parent_id)
    db.add(c)
    await db.commit()
    reloaded = (
        await db.execute(select(Comment).where(Comment.id == c.id))
    ).scalar_one()
    return _out(reloaded, 0, False, 0)


async def toggle_comment_like(
    db: AsyncSession, comment_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[bool, int]:
    existing = (
        await db.execute(
            select(CommentLike).where(
                CommentLike.comment_id == comment_id, CommentLike.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        liked = False
    else:
        db.add(CommentLike(comment_id=comment_id, user_id=user_id))
        liked = True
    await db.commit()
    cnt = await db.execute(
        select(func.count()).select_from(CommentLike).where(CommentLike.comment_id == comment_id)
    )
    return liked, int(cnt.scalar_one())


async def _content_owner(db: AsyncSession, content_id: uuid.UUID) -> uuid.UUID | None:
    res = await db.execute(select(Content.owner_id).where(Content.id == content_id))
    return res.scalar_one_or_none()


async def delete_comment(db: AsyncSession, comment_id: uuid.UUID, user: Profile) -> None:
    c = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise CommentError("Comment not found.")
    owner = await _content_owner(db, c.content_id)
    is_admin = bool(user.role and user.role.name == "admin")
    if not (c.user_id == user.id or owner == user.id or is_admin):
        raise CommentError("Not allowed.")
    await db.delete(c)
    await db.commit()


async def toggle_pin(db: AsyncSession, comment_id: uuid.UUID, user: Profile) -> bool:
    c = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise CommentError("Comment not found.")
    owner = await _content_owner(db, c.content_id)
    is_admin = bool(user.role and user.role.name == "admin")
    if not (owner == user.id or is_admin):
        raise CommentError("Only the content owner can pin.")
    c.is_pinned = not c.is_pinned
    await db.commit()
    return c.is_pinned
