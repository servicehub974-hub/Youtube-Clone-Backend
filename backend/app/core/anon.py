import hashlib
import hmac
import uuid
from dataclasses import dataclass

from app.core.config import get_settings

settings = get_settings()
COOKIE_NAME = "nexus_anon"


def _sig(anon_id: str) -> str:
    return hmac.new(settings.anon_secret.encode(), anon_id.encode(), hashlib.sha256).hexdigest()[:16]


def sign_anon(anon_id: str) -> str:
    return f"{anon_id}.{_sig(anon_id)}"


def verify_anon(value: str | None) -> str | None:
    if not value or "." not in value:
        return None
    anon_id, sig = value.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sig(anon_id)):
        return None
    try:
        uuid.UUID(anon_id)
    except ValueError:
        return None
    return anon_id


def new_anon_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Actor:
    """Whoever is acting — a logged-in user OR an anonymous visitor."""

    user: object | None = None
    anon_id: str | None = None

    @property
    def user_id(self):
        return getattr(self.user, "id", None) if self.user else None

    @property
    def role_name(self):
        role = getattr(self.user, "role", None) if self.user else None
        return getattr(role, "name", None) if role else None
