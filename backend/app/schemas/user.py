from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: str
    email: str | None = None
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    role: str


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    username: str | None = Field(
        default=None, min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$"
    )
    bio: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = None
    cover_url: str | None = None
    website: str | None = None
    location: str | None = None
    links: list | None = None


class RoleUpdate(BaseModel):
    role: str  # 'user' | 'creator' | 'admin'


class UserPublicOut(BaseModel):
    id: str
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    cover_url: str | None = None
    bio: str | None = None
    role: str
    website: str | None = None
    location: str | None = None
    links: list = []
    follower_count: int = 0
    content_count: int = 0
    total_views: int = 0
    joined: str | None = None
    is_following: bool = False
