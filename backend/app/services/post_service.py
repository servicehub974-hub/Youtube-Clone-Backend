import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Follow, Post, PostComment, PostCommentLike, PostLike, PostSave, Profile
from app.schemas.post import PostAuthor, PostCommentOut, PostCreate, PostOut, PostUpdate
from app.services import notification_service
from app.services.content_service import _count, _fmt_time_ago


class PostError(Exception):
    pass


async def _actor(db: AsyncSession, user_id):
    p = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if not p:
        return "Someone", None
    return (p.display_name or p.username or "Someone"), p.avatar_url


def _post_image(post) -> str | None:
    imgs = list(post.images or [])
    return imgs[0] if imgs else (post.video_url if post.video_url else None)


def _author(a: Profile | None, author_id) -> PostAuthor:
    return PostAuthor(
        id=str(author_id),
        name=(a.display_name or a.username or "User") if a else "User",
        avatar=(a.avatar_url if a and a.avatar_url else f"https://i.pravatar.cc/150?u={author_id}"),
        verified=bool(a and a.role and a.role.name in ("creator", "admin")),
    )


def out_from(p: Post, viewer_id, like_count: int, comment_count: int, repost_count: int,
             is_liked: bool, is_saved: bool, is_following: bool, original: PostOut | None = None) -> PostOut:
    return PostOut(
        id=str(p.id), author=_author(p.author, p.author_id),
        title=p.title, body=p.body, video_url=p.video_url, images=list(p.images or []),
        time_ago=_fmt_time_ago(p.created_at),
        like_count=like_count, comment_count=comment_count, repost_count=repost_count,
        is_liked=is_liked, is_saved=is_saved, is_following=is_following,
        is_owner=viewer_id == p.author_id, repost_of=original,
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
            _nm, _av = await _actor(db, author_id)
            notification_service.add(db, orig.author_id, "repost", _nm, "reposted your post", f"/post/{orig.id}", _post_image(orig) or _av)
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
            _nm, _av = await _actor(db, user_id)
            notification_service.add(db, p.author_id, "post_like", _nm, "liked your post", f"/post/{post_id}", _post_image(p) or _av)
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


async def add_comment(db: AsyncSession, post_id: uuid.UUID, author_id: uuid.UUID, body: str, parent_id: str | None = None) -> PostCommentOut:
    pid = None
    if parent_id:
        parent = (await db.execute(select(PostComment).where(PostComment.id == uuid.UUID(parent_id)))).scalar_one_or_none()
        if parent:
            pid = parent.parent_id or parent.id  # collapse to 2 levels
            if parent.author_id and parent.author_id != author_id:
                _nm, _av = await _actor(db, author_id)
                notification_service.add(db, parent.author_id, "reply", _nm, "replied to your comment", f"/post/{post_id}", _av)
    c = PostComment(post_id=post_id, author_id=author_id, body=body.strip(), parent_id=pid)
    db.add(c)
    p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if p and p.author_id != author_id and not pid:
        _nm, _av = await _actor(db, author_id)
        notification_service.add(db, p.author_id, "post_comment", _nm, "commented on your post", f"/post/{post_id}", _post_image(p) or _av)
    await db.commit()
    c = (await db.execute(select(PostComment).where(PostComment.id == c.id))).scalar_one()
    return PostCommentOut(id=str(c.id), author=_author(c.author, c.author_id), body=c.body, time_ago=_fmt_time_ago(c.created_at), parent_id=str(c.parent_id) if c.parent_id else None)


async def toggle_comment_like(db: AsyncSession, comment_id: uuid.UUID, user_id: uuid.UUID):
    row = (await db.execute(select(PostCommentLike).where(PostCommentLike.comment_id == comment_id, PostCommentLike.user_id == user_id))).scalar_one_or_none()
    if row:
        await db.delete(row); liked = False
    else:
        db.add(PostCommentLike(comment_id=comment_id, user_id=user_id)); liked = True
    await db.commit()
    cnt = await _count(db, PostCommentLike, comment_id=comment_id)
    return liked, cnt


async def list_comments(db: AsyncSession, post_id: uuid.UUID, viewer_id=None):
    rows = (await db.execute(
        select(PostComment).where(PostComment.post_id == post_id).order_by(PostComment.created_at.asc())
    )).scalars().all()
    like_counts: dict = {c.id: await _count(db, PostCommentLike, comment_id=c.id) for c in rows}
    liked_set: set = set()
    if viewer_id and rows:
        liked_set = set((await db.execute(
            select(PostCommentLike.comment_id).where(PostCommentLike.user_id == viewer_id)
        )).scalars().all())

    def mk(c):
        return PostCommentOut(
            id=str(c.id), author=_author(c.author, c.author_id), body=c.body,
            time_ago=_fmt_time_ago(c.created_at), like_count=like_counts.get(c.id, 0),
            is_liked=c.id in liked_set, parent_id=str(c.parent_id) if c.parent_id else None, replies=[],
        )

    tops = [mk(c) for c in rows if not c.parent_id]
    by_id = {t.id: t for t in tops}
    for c in rows:
        if c.parent_id and str(c.parent_id) in by_id:
            by_id[str(c.parent_id)].replies.append(mk(c))
    return tops


async def update_post(db: AsyncSession, post_id: uuid.UUID, owner_id: uuid.UUID, data: PostUpdate):
    p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if not p:
        raise PostError("Not found")
    if p.author_id != owner_id:
        raise PostError("Not allowed")
    d = data.model_dump(exclude_unset=True)
    if "title" in d: p.title = d["title"] or None
    if "body" in d: p.body = d["body"] or None
    if "video_url" in d: p.video_url = d["video_url"] or None
    if "images" in d and d["images"] is not None: p.images = d["images"]
    await db.commit()
    return await to_out(db, (await db.execute(select(Post).where(Post.id == post_id))).scalar_one(), owner_id)


async def list_saved(db: AsyncSession, user_id: uuid.UUID, limit: int = 40):
    rows = (await db.execute(
        select(Post).join(PostSave, PostSave.post_id == Post.id)
        .where(PostSave.user_id == user_id).order_by(PostSave.created_at.desc()).limit(limit)
    )).scalars().all()
    return [await to_out(db, p, user_id) for p in rows]


async def list_liked(db: AsyncSession, user_id: uuid.UUID, limit: int = 40):
    rows = (await db.execute(
        select(Post).join(PostLike, PostLike.post_id == Post.id)
        .where(PostLike.user_id == user_id).order_by(PostLike.created_at.desc()).limit(limit)
    )).scalars().all()
    return [await to_out(db, p, user_id) for p in rows]
