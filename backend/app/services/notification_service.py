import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.services.content_service import _fmt_time_ago


def add(session: AsyncSession, recipient_id, ntype: str, actor_name: str | None, message: str, link: str | None):
    """Queue a notification on the session (caller commits). No self-notify."""
    if recipient_id is None:
        return
    session.add(Notification(
        user_id=recipient_id, type=ntype,
        actor_name=actor_name or "Someone", message=message, link=link,
    ))


async def notify(db: AsyncSession, recipient_id, ntype, actor_name, message, link):
    """Standalone notify (own commit)."""
    if recipient_id is None:
        return
    try:
        add(db, recipient_id, ntype, actor_name, message, link)
        await db.commit()
    except Exception:
        await db.rollback()


async def list_notifications(db: AsyncSession, user_id: uuid.UUID, limit: int = 40):
    try:
        rows = (await db.execute(
            select(Notification).where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc()).limit(limit)
        )).scalars().all()
    except Exception:
        await db.rollback()
        return []
    return [
        {"id": str(n.id), "type": n.type, "actor_name": n.actor_name,
         "message": n.message, "link": n.link, "is_read": n.is_read,
         "time_ago": _fmt_time_ago(n.created_at)}
        for n in rows
    ]


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    try:
        r = await db.execute(
            select(func.count()).select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        return int(r.scalar_one())
    except Exception:
        await db.rollback()
        return 0


async def mark_read(db: AsyncSession, user_id: uuid.UUID, notif_id: uuid.UUID):
    await db.execute(update(Notification).where(
        Notification.id == notif_id, Notification.user_id == user_id
    ).values(is_read=True))
    await db.commit()


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID):
    await db.execute(update(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    ).values(is_read=True))
    await db.commit()
