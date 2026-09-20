import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Follow, Post, PostComment, PostLike, PostSave, Profile
from app.schemas.post import PostAuthor, PostCommentOut, PostCreate, PostOut
from app.services import notification_service
from app.services.content_service import _count, _fmt_time_ago


class PostError(Exception):
    pass


def _author(a: Profile | None, author_id) -> PostAuthor:
    return PostAuthor(
        id=str(author_id),
        name=(a.display_name or a.username or "User") if a else "User",
        avatar=(a.avatar_url if a and a.avatar_url else f"https://i.pravatar.cc/150?u={author_id}"),
        verified=bool(a and a.role and a.role.name in ("creator", "admin")),
    )


async def to_out(db: AsyncSession, p: Post, viewer_id: uuid.UUID | None, depth: int = 1) -> PostOut:
    like_count = await _count(db, PostLike, post_id=p.id)
    comment_count = await _count(db, PostComment, post_id=p.id)
    repost_count = await _count(db, Post, repost_of=p.id)
    is_liked = is_saved = is_following = False
    if viewer_id:
        is_liked = (await db.execute(select(PostLike.post_id).where(PostLike.post_id == p.id, PostLike.user_id == viewer_id))).first() is not None
        is_saved = (await db.execute(select(PostSave.post_id).where(PostSave.post_id == p.id, PostSave.user_id == viewer_id))).first() is not None
        is_following = (await db.execute(select(Follow.creator_id).where(Follow.follower_id == viewer_id, Follow.creator_id == p.author_id))).first() is not None
    original = None
    if p.repost_of and depth > 0:
        orig = (await db.execute(select(Post).where(Post.id == p.repost_of))).scalar_one_or_none()
        if orig:
            original = await to_out(db, orig, viewer_id, depth=0)
    return PostOut(
        id=str(p.id), author=_author(p.author, p.author_id),
        title=p.title, body=p.body, video_url=p.video_url, images=list(p.images or []),
        time_ago=_fmt_time_ago(p.created_at),
        like_count=like_count, comment_count=comment_count, repost_count=repost_count,
        is_liked=is_liked, is_saved=is_saved, is_following=is_following,
        is_owner=viewer_id == p.author_id, repost_of=original,
    )


async def create_post(db: AsyncSession, author_id: uuid.UUID, data: PostCreate) -> Post:
    if not (data.title or data.body or data.images or data.video_url or data.repost_of):
        raise PostError("Post is empty.")
    p = Post(
        author_id=author_id, title=(data.title or None), body=(data.body or None),
        video_url=(data.video_url or None), images=data.images or [],
        repost_of=uuid.UUID(data.repost_of) if data.repost_of else None,
    )
    db.add(p)
    if data.repost_of:
        orig = (await db.execute(select(Post).where(Post.id == uuid.UUID(data.repost_of)))).scalar_one_or_none()
        if orig and orig.author_id != author_id:
            notification_service.add(db, orig.author_id, "repost", None, "reposted your post", f"/post/{orig.id}")
    await db.commit()
    return (await db.execute(select(Post).where(Post.id == p.id))).scalar_one()


async def feed(db: AsyncSession, viewer_id, cursor: str | None, limit: int = 10):
    stmt = select(Post).order_by(Post.created_at.desc(), Post.id.desc()).limit(limit + 1)
    if cursor:
        try:
            stmt = stmt.where(Post.created_at < datetime.fromisoformat(cursor))
        except ValueError:
            pass
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [await to_out(db, p, viewer_id) for p in rows]
    nxt = rows[-1].created_at.isoformat() if has_more and rows else None
    return items, nxt


async def list_by_author(db: AsyncSession, author_id: uuid.UUID, viewer_id, limit: int = 30):
    rows = (await db.execute(
        select(Post).where(Post.author_id == author_id).order_by(Post.created_at.desc()).limit(limit)
    )).scalars().all()
    return [await to_out(db, p, viewer_id) for p in rows]


async def get(db: AsyncSession, post_id: uuid.UUID, viewer_id) -> PostOut | None:
    p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    return await to_out(db, p, viewer_id) if p else None


async def delete_post(db: AsyncSession, post_id: uuid.UUID, owner_id: uuid.UUID):
    p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if not p:
        raise PostError("Not found")
    if p.author_id != owner_id:
        raise PostError("Not allowed")
    await db.delete(p)
    await db.commit()


async def toggle_like(db: AsyncSession, post_id: uuid.UUID, user_id: uuid.UUID):
    row = (await db.execute(select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user_id))).scalar_one_or_none()
    if row:
        await db.delete(row); liked = False
    else:
        db.add(PostLike(post_id=post_id, user_id=user_id)); liked = True
        p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
        if p and p.author_id != user_id:
            notification_service.add(db, p.author_id, "post_like", None, "liked your post", f"/post/{post_id}")
    await db.commit()
    return liked, await _count(db, PostLike, post_id=post_id)


async def toggle_save(db: AsyncSession, post_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = (await db.execute(select(PostSave).where(PostSave.post_id == post_id, PostSave.user_id == user_id))).scalar_one_or_none()
    if row:
        await db.delete(row); saved = False
    else:
        db.add(PostSave(post_id=post_id, user_id=user_id)); saved = True
    await db.commit()
    return saved


async def add_comment(db: AsyncSession, post_id: uuid.UUID, author_id: uuid.UUID, body: str) -> PostCommentOut:
    c = PostComment(post_id=post_id, author_id=author_id, body=body.strip())
    db.add(c)
    p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if p and p.author_id != author_id:
        notification_service.add(db, p.author_id, "post_comment", None, "commented on your post", f"/post/{post_id}")
    await db.commit()
    c = (await db.execute(select(PostComment).where(PostComment.id == c.id))).scalar_one()
    return PostCommentOut(id=str(c.id), author=_author(c.author, c.author_id), body=c.body, time_ago=_fmt_time_ago(c.created_at))


async def list_comments(db: AsyncSession, post_id: uuid.UUID):
    rows = (await db.execute(
        select(PostComment).where(PostComment.post_id == post_id).order_by(PostComment.created_at.asc())
    )).scalars().all()
    return [PostCommentOut(id=str(c.id), author=_author(c.author, c.author_id), body=c.body, time_ago=_fmt_time_ago(c.created_at)) for c in rows]
