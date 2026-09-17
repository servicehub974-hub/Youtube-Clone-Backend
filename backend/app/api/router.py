from fastapi import APIRouter

from app.api.routes import (admin, categories, comments, content, features, health, messages, tags, uploads, users)

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(categories.router, tags=["categories"])
api_router.include_router(tags.router, tags=["tags"])
api_router.include_router(content.router, tags=["content"])
api_router.include_router(comments.router, tags=["comments"])
api_router.include_router(uploads.router, tags=["uploads"])
api_router.include_router(features.router, tags=["features"])
api_router.include_router(messages.router, tags=["messages"])
