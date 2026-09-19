"""Tiny in-process TTL cache for hot public reads (single-worker safe)."""
import time

_store: dict[str, tuple[float, object]] = {}


async def cached(key: str, ttl: float, factory):
    now = time.time()
    hit = _store.get(key)
    if hit and hit[0] > now:
        return hit[1]
    val = await factory()
    _store[key] = (now + ttl, val)
    return val


def invalidate(prefix: str = "") -> None:
    for k in [k for k in _store if k.startswith(prefix)]:
        _store.pop(k, None)
