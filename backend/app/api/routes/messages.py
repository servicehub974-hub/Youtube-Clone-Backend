import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_feature
from app.core.db import get_db
from app.models import Profile
from app.services import message_service
from app.services.message_service import MessageError

# Everything here is gated by the "messages" feature flag.
router = APIRouter(
    prefix="/conversations", dependencies=[Depends(require_feature("messages"))]
)


class StartIn(BaseModel):
    user_id: str


class SendIn(BaseModel):
    body: str


@router.post("")
async def start_conversation(
    data: StartIn,
    me: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conv = await message_service.get_or_create_conversation(db, me.id, uuid.UUID(data.user_id))
    except MessageError as e:
        raise HTTPException(400, detail=str(e))
    return {"id": str(conv.id)}


@router.get("")
async def list_conversations(
    me: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await message_service.list_conversations(db, me.id)


@router.get("/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    me: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await message_service.get_messages(db, uuid.UUID(conv_id), me.id)
    except MessageError as e:
        raise HTTPException(403, detail=str(e))


@router.post("/{conv_id}/messages")
async def send_message(
    conv_id: str,
    data: SendIn,
    me: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not data.body.strip():
        raise HTTPException(400, "Empty message")
    try:
        return await message_service.send_message(db, uuid.UUID(conv_id), me.id, data.body, me.display_name or me.username)
    except MessageError as e:
        raise HTTPException(403, detail=str(e))


@router.post("/{conv_id}/read")
async def mark_read(
    conv_id: str,
    me: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await message_service.mark_read(db, uuid.UUID(conv_id), me.id)
    return {"ok": True}
