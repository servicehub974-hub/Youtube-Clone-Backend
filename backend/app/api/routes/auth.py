import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.email import send_email
from app.core.email_templates import password_reset_email, verification_email
from app.core.ratelimit import client_ip, rate_limit
from app.core.security import (
    create_access_token,
    create_reset_token,
    create_verification_token,
    decode_reset_token,
    decode_verification_token,
)
from app.models import User
from app.schemas.auth import (
    AuthOut,
    ForgotPasswordIn,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    TokenIn,
    UserOut,
)
from app.services import auth_service
from app.services.auth_service import AuthError, to_user_out

router = APIRouter(prefix="/auth")
settings = get_settings()


# ---------- cookie helpers ----------
def _set_refresh_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=value,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path="/api/auth")


def _send_verification(background: BackgroundTasks, user: User) -> str:
    token = create_verification_token(user.id)
    link = f"{settings.frontend_url}/verify-email?token={token}"
    subject, html, text = verification_email(link)
    background.add_task(send_email, user.email, subject, html, text)
    return token


# ---------- routes ----------
@router.post(
    "/register",
    response_model=AuthOut,
    dependencies=[Depends(rate_limit(10, 3600))],
)
async def register(
    data: RegisterIn,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_service.register_user(db, data)
    except AuthError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))

    cookie = await auth_service.create_session(
        db, user.id, request.headers.get("user-agent"), client_ip(request)
    )
    _set_refresh_cookie(response, cookie)

    token = _send_verification(background, user)
    access = create_access_token(user.id, user.role.name)
    return AuthOut(
        access_token=access,
        user=to_user_out(user),
        verification_token=(token if settings.environment != "production" else None),
    )


@router.post(
    "/login",
    response_model=AuthOut,
    dependencies=[Depends(rate_limit(15, 300))],
)
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
        db, user.id, request.headers.get("user-agent"), client_ip(request)
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


# ---------- email verification ----------
@router.post("/verify-email")
async def verify_email(payload: TokenIn, db: AsyncSession = Depends(get_db)):
    try:
        data = decode_verification_token(payload.token)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")

    user = await auth_service.get_user(db, uuid.UUID(data["sub"]))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    await auth_service.mark_email_verified(db, user)
    return {"ok": True}


@router.post(
    "/resend-verification",
    dependencies=[Depends(rate_limit(5, 3600))],
)
async def resend_verification(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    _send_verification(background, user)
    return {"ok": True}


# ---------- password reset ----------
@router.post(
    "/forgot-password",
    dependencies=[Depends(rate_limit(5, 3600))],
)
async def forgot_password(
    data: ForgotPasswordIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.get_user_by_email(db, data.email)
    # Always return ok — never reveal whether an email exists.
    if user:
        token = create_reset_token(user.id)
        link = f"{settings.frontend_url}/reset-password?token={token}"
        subject, html, text = password_reset_email(link)
        background.add_task(send_email, user.email, subject, html, text)
    return {"ok": True}


@router.post(
    "/reset-password",
    dependencies=[Depends(rate_limit(10, 3600))],
)
async def reset_password(data: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_reset_token(data.token)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")

    user = await auth_service.get_user(db, uuid.UUID(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    await auth_service.set_password(db, user, data.new_password)
    return {"ok": True}
