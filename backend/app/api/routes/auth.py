from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_verification_token,
    decode_verification_token,
)
from app.core.db import get_db
from app.models import User
from app.schemas.auth import AuthOut, LoginIn, RegisterIn, UserOut
from app.services import auth_service
from app.services.auth_service import AuthError, to_user_out

router = APIRouter(prefix="/auth")
settings = get_settings()


def _set_refresh_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=value,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # "lax" local, "none" cross-site prod
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path="/api/auth")


def _client_ip(request: Request) -> str | None:
    # Behind Render/Cloudflare the real IP is in X-Forwarded-For (first hop).
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/register", response_model=AuthOut)
async def register(
    data: RegisterIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_service.register_user(db, data)
    except AuthError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))

    cookie = await auth_service.create_session(
        db, user.id, request.headers.get("user-agent"), _client_ip(request)
    )
    _set_refresh_cookie(response, cookie)

    access = create_access_token(user.id, user.role.name)
    verification = create_verification_token(user.id)
    return AuthOut(
        access_token=access,
        user=to_user_out(user),
        verification_token=(
            verification if settings.environment != "production" else None
        ),
    )


@router.post("/login", response_model=AuthOut)
async def login(
    data: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_service.authenticate(db, data.identifier, data.password)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e))

    cookie = await auth_service.create_session(
        db, user.id, request.headers.get("user-agent"), _client_ip(request)
    )
    _set_refresh_cookie(response, cookie)

    access = create_access_token(user.id, user.role.name)
    return AuthOut(access_token=access, user=to_user_out(user))


@router.post("/refresh", response_model=AuthOut)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    cookie_value = request.cookies.get(settings.refresh_cookie_name)
    if not cookie_value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="No session")
    try:
        new_cookie, user = await auth_service.rotate_session(db, cookie_value)
    except AuthError as e:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e))

    _set_refresh_cookie(response, new_cookie)
    access = create_access_token(user.id, user.role.name)
    return AuthOut(access_token=access, user=to_user_out(user))


@router.post("/logout")
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    cookie_value = request.cookies.get(settings.refresh_cookie_name)
    if cookie_value:
        await auth_service.revoke_session(db, cookie_value)
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.revoke_all_sessions(db, user.id)
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return to_user_out(user)


@router.post("/verify-email")
async def verify_email(
    payload: dict, db: AsyncSession = Depends(get_db)
):
    token = payload.get("token", "")
    try:
        data = decode_verification_token(token)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    import uuid

    user = await auth_service.get_user(db, uuid.UUID(data["sub"]))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    user.email_verified = True
    await db.commit()
    return {"ok": True}
