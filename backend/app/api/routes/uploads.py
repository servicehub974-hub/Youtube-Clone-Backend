import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_role
from app.core.storage import get_storage
from app.models import Profile

router = APIRouter(prefix="/uploads")


class SignIn(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"


@router.post("/sign")
async def sign_upload(
    data: SignIn,
    _user: Profile = Depends(require_role("creator", "admin")),
):
    ext = ""
    if "." in data.filename:
        ext = "." + data.filename.rsplit(".", 1)[-1].lower()[:8]
    now = datetime.now(timezone.utc)
    path = f"{now:%Y/%m}/{uuid.uuid4().hex}{ext}"
    try:
        return await get_storage().create_signed_upload(path, data.content_type)
    except NotImplementedError as e:
        raise HTTPException(501, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, detail=f"Storage error: {str(e)[:200]}")
