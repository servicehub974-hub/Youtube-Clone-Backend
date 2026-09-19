from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


app.include_router(api_router, prefix="/api")


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"name": settings.app_name, "status": "ok", "docs": "/docs"}


@app.api_route("/api/ping", methods=["GET", "HEAD"])
def ping():
    # Lightweight keep-alive endpoint (no DB) for UptimeRobot / cron pings.
    return {"ok": True}
