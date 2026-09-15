"""
Content feed endpoint.

NOTE: this serves deterministic *placeholder* seed data so the themed home
feed + infinite scroll work end-to-end right now. The API contract (cursor
pagination, item shape) is real and stays; Phase 2 swaps the seed generator
for real database content without changing the frontend.
"""
import base64
import hashlib

from fastapi import APIRouter, Query

router = APIRouter()

TITLES = [
    "Echoes of Neon: Tokyo 2077",
    "Volumetric Lighting Masterclass",
    "Obsidian UI: Dark Mode Kit",
    "Abstract Fluid Dynamics 4K",
    "Cinematic LUTs: The Dune Collection",
    "Space Station Alpha - 3D Environment",
    "Ethereal Vocals & Ambient Synths",
    "Macro Textures: Organic Matter",
    "Holographic Projections Bundle",
    "Drone Flights: The Alps in 8K",
]

IMAGES = [
    "https://images.unsplash.com/photo-1605810230434-7631ac76ec81?q=80&w=1200",
    "https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=1200",
    "https://images.unsplash.com/photo-1536240478700-b869070f9279?q=80&w=1200",
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=1200",
    "https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=1200",
    "https://images.unsplash.com/photo-1614113489855-66422ad300a4?q=80&w=1200",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=1200",
    "https://images.unsplash.com/photo-1493612276216-ee3925520721?q=80&w=1200",
    "https://images.unsplash.com/photo-1616423640778-28d1b53229bd?q=80&w=1200",
    "https://images.unsplash.com/photo-1582738411706-bfc8e691d1c2?q=80&w=1200",
]

CREATORS = ["Aura Visuals", "Nexus Labs", "Elena M.", "Void Arts", "Vertex", "Kira"]
TIERS = ["free", "free", "free", "gems", "gems", "vip"]

TOTAL = 48  # placeholder catalogue size; feed ends gracefully after this


def _rng(i: int, salt: str) -> float:
    """Deterministic pseudo-random 0..1 so an item looks identical across pages."""
    h = hashlib.md5(f"{i}-{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _item(i: int) -> dict:
    is_video = _rng(i, "v") > 0.3
    tier = TIERS[int(_rng(i, "t") * len(TIERS))]
    return {
        "id": f"seed_{i}",
        "title": TITLES[i % len(TITLES)],
        "thumbnail": IMAGES[i % len(IMAGES)],
        "is_video": is_video,
        "duration": (
            f"{int(_rng(i, 'd') * 10 + 1)}:{int(_rng(i, 's') * 59):02d}"
            if is_video
            else None
        ),
        "creator": {
            "name": CREATORS[i % len(CREATORS)],
            "avatar": f"https://i.pravatar.cc/150?u={i + 100}",
            "verified": _rng(i, "c") > 0.4,
        },
        "tier": tier,
        "price_gems": int(_rng(i, "p") * 5 + 1) * 100 if tier == "gems" else None,
        "views": f"{_rng(i, 'w') * 500 + 10:.1f}K",
        "time_ago": f"{int(_rng(i, 'a') * 24 + 1)}h",
    }


def _decode(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 0


def _encode(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


@router.get("/content")
def list_content(
    limit: int = Query(12, ge=1, le=50),
    cursor: str | None = None,
    category: str | None = None,  # accepted now; real filtering lands in Phase 2
):
    start = _decode(cursor)
    end = min(start + limit, TOTAL)
    items = [_item(i) for i in range(start, end)]
    next_cursor = _encode(end) if end < TOTAL else None
    return {"items": items, "next_cursor": next_cursor}
