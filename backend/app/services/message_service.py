import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message, Profile
from app.services.content_service import _fmt_time_ago
from app.services import notification_service


class MessageError(Exception):
    pass


def _ordered(u1: uuid.UUID, u2: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return tuple(sorted([u1, u2], key=str))  # type: ignore[return-value]


async def get_or_create_conversation(
    db: AsyncSession, me: uuid.UUID, other: uuid.UUID
) -> Conversation:
    if me == other:
        raise MessageError("You can't message yourself.")
    a, b = _ordered(me, other)
    existing = (
        await db.execute(
            select(Conversation).where(
                Conversation.participant_a == a, Conversation.participant_b == b
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    conv = Conversation(participant_a=a, participant_b=b, last_message_at=datetime.now(timezone.utc))
    db.add(conv)
    await db.commit()
    return (
        await db.execute(select(Conversation).where(Conversation.id == conv.id))
    ).scalar_one()


async def _is_participant(db: AsyncSession, conv_id: uuid.UUID, me: uuid.UUID) -> Conversation | None:
    conv = (
        await db.execute(select(Conversation).where(Conversation.id == conv_id))
    ).scalar_one_or_none()
    if not conv or me not in (conv.participant_a, conv.participant_b):
        return None
    return conv


async def list_conversations(db: AsyncSession, me: uuid.UUID) -> list[dict]:
    _vipmap = {}
    convs = (
        await db.execute(
            select(Conversation)
            .where(or_(Conversation.participant_a == me, Conversation.participant_b == me))
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
    ).scalars().all()

    out = []
    for c in convs:
        other_id = c.participant_b if c.participant_a == me else c.participant_a
        other = (await db.execute(select(Profile).where(Profile.id == other_id))).scalar_one_or_none()
        last = (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == c.id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        unread = (
            await db.execute(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == c.id,
                    Message.sender_id != me,
                    Message.read_at.is_(None),
                )
            )
        ).scalar_one()
        out.append(
            {
                "id": str(c.id),
                "other": {
                    "id": str(other_id),
                    "name": (other.display_name or other.username or "User") if other else "User",
                    "avatar": (other.avatar_url if other and other.avatar_url else f"https://i.pravatar.cc/150?u={other_id}"),
                    "vip_tier": _vipmap.get(other_id),
                },
                "last_message": last.body if last else "",
                "last_at": _fmt_time_ago(last.created_at) if last else "",
                "unread": int(unread),
            }
        )
    try:
        from app.services import monetization_service as _mon
        import uuid as _uuid
        oids = [_uuid.UUID(o["other"]["id"]) for o in out]
        vm = await _mon.active_vip_map(db, oids)
        for o in out:
            o["other"]["vip_tier"] = vm.get(_uuid.UUID(o["other"]["id"]))
    except Exception:
        pass
    return out


async def get_messages(db: AsyncSession, conv_id: uuid.UUID, me: uuid.UUID) -> list[dict]:
    if not await _is_participant(db, conv_id, me):
        raise MessageError("Not allowed.")
    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
            .limit(200)
        )
    ).scalars().all()
    return [
        {"id": str(m.id), "sender_id": str(m.sender_id), "body": m.body, "created_at": m.created_at.isoformat()}
        for m in rows
    ]


async def send_message(db: AsyncSession, conv_id: uuid.UUID, me: uuid.UUID, body: str, sender_name: str | None = None) -> dict:
    conv = await _is_participant(db, conv_id, me)
    if not conv:
        raise MessageError("Not allowed.")
    m = Message(conversation_id=conv_id, sender_id=me, body=body.strip())
    db.add(m)
    conv.last_message_at = datetime.now(timezone.utc)
    recipient = conv.participant_a if conv.participant_b == me else conv.participant_b
    try:
        notification_service.add(db, recipient, "message", sender_name or "Someone", "sent you a message", f"/messages?c={conv_id}")
    except Exception:
        pass
    await db.commit()
    reloaded = (await db.execute(select(Message).where(Message.id == m.id))).scalar_one()
    return {"id": str(reloaded.id), "sender_id": str(me), "body": reloaded.body, "created_at": reloaded.created_at.isoformat()}


async def mark_read(db: AsyncSession, conv_id: uuid.UUID, me: uuid.UUID) -> None:
    if not await _is_participant(db, conv_id, me):
        return
    await db.execute(
        update(Message)
        .where(
            Message.conversation_id == conv_id,
            Message.sender_id != me,
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def edit_message(db: AsyncSession, conv_id: uuid.UUID, msg_id: uuid.UUID, me: uuid.UUID, body: str):
    m = (await db.execute(select(Message).where(Message.id == msg_id, Message.conversation_id == conv_id))).scalar_one_or_none()
    if not m:
        raise MessageError("Message not found")
    if m.sender_id != me:
        raise MessageError("Not allowed")
    m.body = body.strip()
    await db.commit()
    return {"id": str(m.id), "body": m.body}


async def delete_message(db: AsyncSession, conv_id: uuid.UUID, msg_id: uuid.UUID, me: uuid.UUID):
    m = (await db.execute(select(Message).where(Message.id == msg_id, Message.conversation_id == conv_id))).scalar_one_or_none()
    if not m:
        raise MessageError("Message not found")
    if m.sender_id != me:
        raise MessageError("Not allowed")
    await db.delete(m)
    await db.commit()
