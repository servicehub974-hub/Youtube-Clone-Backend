import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import Profile, Session as SessionModel, User
from app.schemas.auth import RegisterIn, UserOut

settings = get_settings()


class AuthError(Exception):
    """Raised for expected auth failures (mapped to 4xx in routes)."""


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        role=user.role.name if user.role else "user",
        email_verified=user.email_verified,
        avatar_url=user.profile.avatar_url if user.profile else None,
    )


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(select(User).where(User.email == email))
    return res.scalar_one_or_none()


async def set_password(db: AsyncSession, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    await db.commit()
    # Security: invalidate all existing sessions after a password change.
    await revoke_all_sessions(db, user.id)


async def mark_email_verified(db: AsyncSession, user: User) -> None:
    user.email_verified = True
    await db.commit()


async def register_user(db: AsyncSession, data: RegisterIn) -> User:
    exists = await db.execute(
        select(User.id).where(
            or_(User.email == data.email, User.username == data.username)
        )
    )
    if exists.first():
        raise AuthError("That email or username is already taken.")

    user = User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name or data.username,
        role_id=1,  # 'user'
    )
    db.add(user)
    await db.flush()
    db.add(Profile(user_id=user.id))
    await db.commit()
    reloaded = await get_user(db, user.id)
    assert reloaded is not None
    return reloaded


async def authenticate(db: AsyncSession, identifier: str, password: str) -> User:
    res = await db.execute(
        select(User).where(
            or_(User.email == identifier, User.username == identifier)
        )
    )
    user = res.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise AuthError("Incorrect email/username or password.")
    if user.status != "active":
        raise AuthError("This account is not active.")
    return user


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    user_agent: str | None,
    ip: str | None,
) -> str:
    """Creates a session row and returns the cookie value: '<session_id>.<raw_token>'."""
    import ipaddress

    safe_ip: str | None = None
    if ip:
        try:
            safe_ip = str(ipaddress.ip_address(ip))
        except ValueError:
            safe_ip = None

    raw = generate_refresh_token()
    session = SessionModel(
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(raw),
        user_agent=(user_agent or "")[:400] or None,
        ip=safe_ip,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    await db.commit()
    return f"{session.id}.{raw}"


async def rotate_session(db: AsyncSession, cookie_value: str) -> tuple[str, User]:
    """Validates + rotates a refresh session. Returns (new_cookie_value, user)."""
    try:
        session_id_str, raw = cookie_value.split(".", 1)
        session_id = uuid.UUID(session_id_str)
    except (ValueError, AttributeError):
        raise AuthError("Invalid session.")

    res = await db.execute(select(SessionModel).where(SessionModel.id == session_id))
    session = res.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if (
        not session
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.refresh_token_hash != hash_refresh_token(raw)
    ):
        raise AuthError("Session expired or invalid.")

    new_raw = generate_refresh_token()
    session.refresh_token_hash = hash_refresh_token(new_raw)
    session.expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    await db.commit()

    user = await get_user(db, session.user_id)
    if not user or user.status != "active":
        raise AuthError("User not available.")
    return f"{session.id}.{new_raw}", user


async def revoke_session(db: AsyncSession, cookie_value: str) -> None:
    try:
        session_id = uuid.UUID(cookie_value.split(".", 1)[0])
    except (ValueError, AttributeError):
        return
    await db.execute(
        update(SessionModel)
        .where(SessionModel.id == session_id, SessionModel.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(SessionModel)
        .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
