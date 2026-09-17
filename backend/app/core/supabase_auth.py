import jwt
from jwt import PyJWKClient

from app.core.config import get_settings

settings = get_settings()

_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient | None:
    """Cached JWKS client for verifying asymmetric (ES256/RS256) Supabase tokens."""
    global _jwks_client
    if _jwks_client is None and settings.supabase_url:
        url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url)
    return _jwks_client


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase access token.

    Supports BOTH signing modes:
      - HS256  → verified with the project's legacy JWT secret.
      - ES256/RS256 (new asymmetric signing keys) → verified via the project JWKS.
    Returns the claims dict (`sub` = auth user id, `email`, …).
    """
    alg = jwt.get_unverified_header(token).get("alg", "HS256")

    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise ValueError("SUPABASE_JWT_SECRET not configured")
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )

    # Asymmetric signing keys
    client = _jwks()
    if client is None:
        raise ValueError("SUPABASE_URL required to verify asymmetric tokens")
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
    )
