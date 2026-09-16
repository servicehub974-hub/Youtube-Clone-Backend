from pydantic import BaseModel, Field


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: str | None = None


class CommentAuthor(BaseModel):
    id: str
    name: str
    avatar: str
    verified: bool


class CommentOut(BaseModel):
    id: str
    parent_id: str | None = None
    body: str
    time_ago: str
    author: CommentAuthor
    like_count: int
    is_liked: bool
    reply_count: int
    is_pinned: bool
