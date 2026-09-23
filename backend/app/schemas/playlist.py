from pydantic import BaseModel, Field

from app.schemas.content import ContentCardOut


class PlaylistIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: str = "public"


class PlaylistUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = None
    visibility: str | None = None


class PlaylistOut(BaseModel):
    id: str
    title: str
    description: str | None = None
    visibility: str
    item_count: int
    thumbnail: str | None = None
    owner_id: str
    contains: bool = False  # set when queried with a content_id


class PlaylistDetailOut(BaseModel):
    id: str
    title: str
    description: str | None = None
    visibility: str
    owner_id: str
    owner_name: str
    is_owner: bool
    items: list[ContentCardOut]


class ReorderIn(BaseModel):
    content_ids: list[str]


class AddItemIn(BaseModel):
    content_id: str
