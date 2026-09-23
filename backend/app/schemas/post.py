from __future__ import annotations

from pydantic import BaseModel, Field


class PostAuthor(BaseModel):
    id: str
    name: str
    avatar: str
    verified: bool = False
    vip_tier: str | None = None


class PostCreate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=8000)
    video_url: str | None = None
    images: list[str] = []
    repost_of: str | None = None


class PostUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    video_url: str | None = None
    images: list[str] | None = None


class PostOut(BaseModel):
    id: str
    author: PostAuthor
    title: str | None = None
    body: str | None = None
    video_url: str | None = None
    images: list[str] = []
    time_ago: str
    like_count: int = 0
    comment_count: int = 0
    repost_count: int = 0
    is_liked: bool = False
    is_saved: bool = False
    is_following: bool = False
    is_owner: bool = False
    repost_of: PostOut | None = None


class PostFeedOut(BaseModel):
    items: list[PostOut]
    next_cursor: str | None = None


class PostCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: str | None = None


class PostCommentOut(BaseModel):
    id: str
    author: PostAuthor
    body: str
    time_ago: str
    like_count: int = 0
    is_liked: bool = False
    parent_id: str | None = None
    replies: list["PostCommentOut"] = []


PostOut.model_rebuild()
PostCommentOut.model_rebuild()
