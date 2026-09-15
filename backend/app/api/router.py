from fastapi import APIRouter

from app.api.routes import admin, content, health, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(content.router, tags=["content"])
