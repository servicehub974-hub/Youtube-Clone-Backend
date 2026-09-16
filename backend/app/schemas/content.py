from pydantic import BaseModel, Field


# --- Categories ---
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    parent_id: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    cover_url: str | None = None
    position: int = 0
    is_active: bool = True


class CategoryOut(BaseModel):
    id: str
    parent_id: str | None = None
    name: str
    slug: str
    description: str | None = None
    thumbnail_url: str | None = None
    position: int
    is_active: bool


# --- Tags ---
class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    status: str = "active"


class TagOut(BaseModel):
    id: str
    name: str
    slug: str
    status: str


# --- Content ---
class ContentIn(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=5000)
    content_type: str = "video"  # video | photo | link
    category_id: str | None = None
    thumbnail_url: str | None = None
    media_url: str | None = None
    duration_seconds: int | None = None
    visibility: str = "public"
    is_premium: bool = False
    price_gems: int | None = None
    allow_comments: bool = True
    tags: list[str] = []  # tag names


class Creator(BaseModel):
    name: str
    avatar: str
    verified: bool


class ContentCardOut(BaseModel):
    """Shape consumed by the frontend feed/card."""

    id: str
    title: str
    thumbnail: str
    is_video: bool
    duration: str | None
    creator: Creator
    tier: str  # free | gems | vip
    price_gems: int | None
    views: str
    time_ago: str


class FeedOut(BaseModel):
    items: list[ContentCardOut]
    next_cursor: str | None


class CategoryRef(BaseModel):
    name: str
    slug: str


class ContentDetailOut(BaseModel):
    id: str
    title: str
    description: str | None
    content_type: str
    media_url: str | None
    thumbnail_url: str | None
    duration: str | None
    is_premium: bool
    price_gems: int | None
    tier: str
    views: int
    views_display: str
    time_ago: str
    creator: Creator
    category: CategoryRef | None
    tags: list[str]
