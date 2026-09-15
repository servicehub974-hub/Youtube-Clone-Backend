import jwt

from app.core.config import get_settings

settings = get_settings()


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase-issued access token (HS256 legacy JWT secret).

    Returns the claims dict (contains `sub` = auth user id, `email`, etc.).
    Raises jwt exceptions on failure.
    """
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience="authenticated",
    )
