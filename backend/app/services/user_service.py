import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Profile, Role
from app.schemas.user import ProfileUpdate, UserOut


class UserError(Exception):
    pass


def to_user_out(profile: Profile) -> UserOut:
    return UserOut(
        id=str(profile.id),
        email=getattr(profile, "email", None),
        username=profile.username,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        bio=profile.bio,
        role=profile.role.name if profile.role else "user",
    )


async def _get(db: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    res = await db.execute(select(Profile).where(Profile.id == user_id))
    return res.scalar_one_or_none()


async def get_or_create_profile(
    db: AsyncSession, user_id_str: str, email: str | None
) -> Profile:
    """Fetch the profile (created by the DB trigger on signup). Falls back to
    creating one if it's somehow missing."""
    user_id = uuid.UUID(user_id_str)
    profile = await _get(db, user_id)

    if profile is None:
        base = (email.split("@")[0] if email else "user")
        profile = Profile(
            id=user_id,
            username=f"{base}-{str(user_id)[:5]}",
            display_name=base,
            role_id=1,
        )
        db.add(profile)
        try:
            await db.commit()
        except Exception:
            await db.rollback()  # trigger created it concurrently
        profile = await _get(db, user_id)

    profile.email = email  # transient, for serialization only
    return profile


async def update_profile(
    db: AsyncSession, profile: Profile, data: ProfileUpdate
) -> Profile:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    refreshed = await _get(db, profile.id)
    assert refreshed is not None
    refreshed.email = getattr(profile, "email", None)
    return refreshed


async def _role_id(db: AsyncSession, role_name: str) -> int:
    res = await db.execute(select(Role.id).where(Role.name == role_name))
    rid = res.scalar_one_or_none()
    if rid is None:
        raise UserError(f"Unknown role: {role_name}")
    return rid


async def set_role(db: AsyncSession, user_id: uuid.UUID, role_name: str) -> Profile:
    profile = await _get(db, user_id)
    if not profile:
        raise UserError("User not found")
    profile.role_id = await _role_id(db, role_name)
    await db.commit()
    return await _get(db, user_id)  # type: ignore[return-value]


async def become_creator(db: AsyncSession, profile: Profile) -> Profile:
    if profile.role and profile.role.name == "admin":
        return profile  # don't downgrade admins
    profile.role_id = await _role_id(db, "creator")
    await db.commit()
    updated = await _get(db, profile.id)
    assert updated is not None
    updated.email = getattr(profile, "email", None)
    return updated


async def list_profiles(db: AsyncSession, limit: int = 50) -> list[Profile]:
    res = await db.execute(
        select(Profile).order_by(Profile.created_at.desc()).limit(limit)
    )
    return list(res.scalars().all())


async def toggle_follow(
    db: AsyncSession, follower_id: uuid.UUID, creator_id: uuid.UUID
) -> tuple[bool, int]:
    from sqlalchemy import func
    from app.models import Follow

    if follower_id == creator_id:
        raise UserError("You can't follow yourself.")

    existing = await db.execute(
        select(Follow).where(
            Follow.follower_id == follower_id, Follow.creator_id == creator_id
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        await db.delete(row)
        following = False
    else:
        db.add(Follow(follower_id=follower_id, creator_id=creator_id))
        following = True
    await db.commit()
    cnt = await db.execute(
        select(func.count()).select_from(Follow).where(Follow.creator_id == creator_id)
    )
    return following, int(cnt.scalar_one())


async def get_public_profile(
    db: AsyncSession, user_id: uuid.UUID, current_user_id: uuid.UUID | None
):
    from sqlalchemy import func
    from app.models import Content, Follow
    from app.schemas.user import UserPublicOut

    p = await _get(db, user_id)
    if not p:
        return None

    fc = await db.execute(
        select(func.count()).select_from(Follow).where(Follow.creator_id == user_id)
    )
    cc = await db.execute(
        select(func.count()).select_from(Content).where(
            Content.owner_id == user_id,
            Content.status == "published",
            Content.visibility == "public",
        )
    )
    is_following = False
    if current_user_id:
        fl = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user_id, Follow.creator_id == user_id
            )
        )
        is_following = fl.scalar_one_or_none() is not None

    return UserPublicOut(
        id=str(p.id),
        username=p.username,
        display_name=p.display_name,
        avatar_url=p.avatar_url,
        cover_url=p.cover_url,
        bio=p.bio,
        role=p.role.name if p.role else "user",
        follower_count=int(fc.scalar_one()),
        content_count=int(cc.scalar_one()),
        is_following=is_following,
    )
