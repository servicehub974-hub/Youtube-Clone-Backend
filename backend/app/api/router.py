from fastapi import APIRouter

from app.api.routes import content, health

# All route modules get registered here. New feature routers (auth, search,
# gems, etc.) are added in later phases.
api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(content.router, tags=["content"])
