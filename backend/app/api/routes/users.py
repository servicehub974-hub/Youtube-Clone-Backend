from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Profile
from app.schemas.user import ProfileUpdate, UserOut, UserPublicOut
from app.schemas.content import ContentCardOut
from app.services import content_service, notification_service, playlist_service
from app.services import user_service
from app.services.user_service import UserError, to_user_out

router = APIRouter(prefix="/users")
settings = get_settings()


@router.get("/me", response_model=UserOut)
async def me(user: Profile = Depends(get_current_user)):
    return to_user_out(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    data: ProfileUpdate,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await user_service.update_profile(db, user, data)
    updated.email = getattr(user, "email", None)
    return to_user_out(updated)


@router.post("/me/become-creator", response_model=UserOut)
async def become_creator(
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.allow_self_creator:
        # If self-serve is disabled, this would become an application/approval
        # flow handled by admins. For now just return current state.
        return to_user_out(user)
    updated = await user_service.become_creator(db, user)
    return to_user_out(updated)


@router.post("/{creator_id}/follow")
async def follow_user(
    creator_id: str,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    from fastapi import HTTPException

    try:
        following, count = await user_service.toggle_follow(
            db, user.id, _uuid.UUID(creator_id)
        )
    except UserError as e:
        raise HTTPException(400, detail=str(e))
    if following:
        await notification_service.notify(
            db, _uuid.UUID(creator_id), "follow",
            user.display_name or user.username, "started following you",
            f"/channel/{user.id}", None, user.avatar_url,
        )
    return {"following": following, "follower_count": count}


@router.get("/{user_id}", response_model=UserPublicOut)
async def public_profile(
    user_id: str,
    viewer: Profile | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    from fastapi import HTTPException

    prof = await user_service.get_public_profile(
        db, _uuid.UUID(user_id), viewer.id if viewer else None
    )
    if not prof:
        raise HTTPException(404, "User not found")
    return prof


@router.get("/{user_id}/content", response_model=list[ContentCardOut])
async def user_content(
    user_id: str, kind: str | None = None, db: AsyncSession = Depends(get_db)
):
    import uuid as _uuid

    return await content_service.list_by_owner_public(db, _uuid.UUID(user_id), kind)


@router.get("/me/anon-activity")
async def anon_activity(
    request: Request,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.anon import verify_anon
    anon_id = verify_anon(request.cookies.get("nexus_anon"))
    if not anon_id:
        return {"has": False}
    try:
        return {"has": await user_service.has_anon_activity(db, anon_id)}
    except Exception:
        return {"has": False}


@router.post("/me/merge-anon")
async def merge_anon(
    request: Request,
    response: Response,
    user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.anon import verify_anon
    anon_id = verify_anon(request.cookies.get("nexus_anon"))
    if anon_id:
        try:
            await user_service.merge_anon(db, user.id, anon_id)
        except Exception:
            await db.rollback()
    response.delete_cookie("nexus_anon", path="/")
    return {"ok": True, "merged": bool(anon_id)}


@router.post("/me/discard-anon")
async def discard_anon(response: Response, _user: Profile = Depends(get_current_user)):
    response.delete_cookie("nexus_anon", path="/")
    return {"ok": True}


@router.get("/{user_id}/playlists")
async def user_playlists(user_id: str, db: AsyncSession = Depends(get_db)):
    import uuid as _uuid
    return await playlist_service.list_public(db, _uuid.UUID(user_id))


@router.post("/{user_id}/block")
async def block_user(user_id: str, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    import uuid as _uuid
    try:
        blocked = await user_service.toggle_block(db, user.id, _uuid.UUID(user_id))
    except UserError as e:
        raise HTTPException(400, detail=str(e))
    return {"blocked": blocked}


@router.get("/me/blocked")
async def my_blocked(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await user_service.list_blocked(db, user.id)


@router.get("/{user_id}/following")
async def user_following(user_id: str, db: AsyncSession = Depends(get_db)):
    import uuid as _uuid
    return await user_service.list_following(db, _uuid.UUID(user_id))
