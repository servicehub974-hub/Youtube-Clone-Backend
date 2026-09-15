from fastapi import APIRouter

from app.api.routes import health

# All route modules get registered here. New feature routers (auth, content,
# search, etc.) are added in later phases.
api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
