"""
Lightweight per-IP rate limiting.

In-memory + per-process — fine for a single worker (current setup). Phase 11
swaps this for a Redis-backed limiter that works across workers/instances.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_buckets: dict[str, list[float]] = defaultdict(list)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(max_calls: int, window_seconds: int):
    """Dependency factory: allow `max_calls` per `window_seconds` per IP+path."""

    async def dependency(request: Request) -> None:
        key = f"{request.url.path}:{client_ip(request)}"
        now = time.time()
        cutoff = now - window_seconds
        bucket = _buckets[key]

        # drop timestamps outside the window
        i = 0
        while i < len(bucket) and bucket[i] < cutoff:
            i += 1
        if i:
            del bucket[:i]

        if len(bucket) >= max_calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again shortly.",
            )
        bucket.append(now)

    return dependency
