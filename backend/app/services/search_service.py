import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Content, SearchHistory
from app.services.content_service import to_card

# English + Bangla/Banglish stop words to ignore when scoring
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "in", "on",
    "for", "and", "or", "do", "you", "have", "has", "any", "there", "with", "my",
    "me", "i", "it", "this", "that", "how", "what", "can", "please", "want",
    "ki", "ache", "ase", "naki", "kore", "korbo", "kora", "amar", "ei", "oi",
    "course", "video", "koro",
    "কি", "আছে", "নাকি", "কোর্স", "আমার", "একটা",
}

SORTS = {"relevance", "newest", "oldest", "most_viewed", "most_liked", "most_discussed"}


def keywords(q: str) -> list[str]:
    toks = [t for t in "".join(c if c.isalnum() or c.isspace() else " " for c in q.lower()).split() if len(t) > 1]
    kept = [t for t in toks if t not in STOPWORDS]
    return kept or toks or ([q.strip().lower()] if q.strip() else [])


def _order_clause(sort: str) -> str:
    return {
        "newest": "s.published_at desc nulls last",
        "oldest": "s.published_at asc nulls last",
        "most_viewed": "s.views desc",
        "most_liked": "s.like_count desc, s.views desc",
        "most_discussed": "s.comment_count desc, s.views desc",
    }.get(sort, "s.score desc, s.views desc")  # relevance default


async def search(
    db: AsyncSession, q: str, *, content_type: str | None = None,
    category: str | None = None, free: str | None = None,
    sort: str = "relevance", limit: int = 30,
):
    kws = keywords(q)
    if not kws:
        return [], 0

    params: dict = {"lim": limit}
    keys: list[str] = []
    for i, kw in enumerate(kws):
        k = f"k{i}"
        params[k] = f"%{kw}%"
        keys.append(k)

    def any_ilike(col: str) -> str:
        return "(" + " or ".join(f"{col} ilike :{k}" for k in keys) + ")"

    title_m = any_ilike("c.title")
    desc_m = any_ilike("coalesce(c.description,'')")
    tag_m = ("exists(select 1 from content_tags ct join tags t on t.id = ct.tag_id "
             f"where ct.content_id = c.id and {any_ilike('t.name')})")
    cat_m = f"exists(select 1 from categories cat where cat.id = c.category_id and {any_ilike('cat.name')})"
    creator_m = (
        "exists(select 1 from profiles p where p.id = c.owner_id and ("
        + any_ilike("coalesce(p.display_name,'')") + " or "
        + any_ilike("coalesce(p.username,'')") + "))"
    )

    score = (f"(case when {title_m} then 3 else 0 end)"
             f" + (case when {tag_m} then 2 else 0 end)"
             f" + (case when {cat_m} then 2 else 0 end)"
             f" + (case when {creator_m} then 1 else 0 end)"
             f" + (case when {desc_m} then 1 else 0 end)")

    filters = ""
    if content_type in ("video", "photo", "link", "post"):
        filters += " and c.content_type = :ctype"; params["ctype"] = content_type
    if category:
        filters += " and c.category_id = (select id from categories where slug = :cat)"; params["cat"] = category
    if free == "free":
        filters += " and coalesce(c.is_premium, false) = false"
    elif free == "premium":
        filters += " and coalesce(c.is_premium, false) = true"

    order = _order_clause(sort if sort in SORTS else "relevance")

    sql = f"""
      select s.id from (
        select c.id, c.published_at, c.views,
          (select count(*) from likes where content_id = c.id) as like_count,
          (select count(*) from comments where content_id = c.id) as comment_count,
          {score} as score
        from content c
        where c.status = 'published' and c.visibility = 'public' {filters}
      ) s
      where s.score > 0
      order by {order}
      limit :lim
    """
    rows = (await db.execute(text(sql), params)).mappings().all()
    ids = [r["id"] for r in rows]
    if not ids:
        return [], 0
    found = (await db.execute(select(Content).where(Content.id.in_(ids)))).scalars().all()
    by_id = {c.id: c for c in found}
    cards = [to_card(by_id[i]) for i in ids if i in by_id]
    return cards, len(cards)


async def suggestions(db: AsyncSession, q: str, limit: int = 8) -> list[str]:
    if not q.strip():
        return []
    p = f"%{q.strip().lower()}%"
    rows = (await db.execute(text("""
        (select distinct title as s from content
          where status='published' and visibility='public' and title ilike :p limit :lim)
        union
        (select distinct name as s from tags where name ilike :p limit :lim)
        limit :lim
    """), {"p": p, "lim": limit})).scalars().all()
    return list(dict.fromkeys(rows))[:limit]


async def trending(db: AsyncSession, limit: int = 8) -> list[str]:
    rows = (await db.execute(text("""
        select lower(query) as q, count(*) as c
        from search_history
        where created_at > now() - interval '7 days' and results_count > 0
        group by lower(query)
        order by c desc, max(created_at) desc
        limit :lim
    """), {"lim": limit})).mappings().all()
    return [r["q"] for r in rows]


async def recent(db: AsyncSession, user_id: uuid.UUID | None, anon_id: str | None, limit: int = 10):
    if user_id:
        where = "user_id = :u"; params = {"u": user_id, "lim": limit}
    elif anon_id:
        where = "anon_id = :a"; params = {"a": anon_id, "lim": limit}
    else:
        return []
    rows = (await db.execute(text(f"""
        select distinct on (lower(query)) id, query, created_at
        from search_history where {where}
        order by lower(query), created_at desc
    """), params)).mappings().all()
    items = sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]
    return [{"id": str(r["id"]), "query": r["query"]} for r in items]


async def record(db: AsyncSession, user_id, anon_id, query: str, results_count: int):
    if not query.strip():
        return
    db.add(SearchHistory(user_id=user_id, anon_id=None if user_id else anon_id,
                         query=query.strip()[:120], results_count=results_count))
    await db.commit()


async def delete_recent(db: AsyncSession, entry_id: uuid.UUID, user_id, anon_id):
    where = "id = :id and " + ("user_id = :u" if user_id else "anon_id = :a")
    params = {"id": entry_id}
    params["u" if user_id else "a"] = user_id or anon_id
    await db.execute(text(f"delete from search_history where {where}"), params)
    await db.commit()


async def search_posts(db: AsyncSession, q: str, viewer_id=None, limit: int = 20):
    kws = keywords(q)
    if not kws:
        return []
    params: dict = {"lim": limit}
    keys: list[str] = []
    for i, kw in enumerate(kws):
        k = f"k{i}"; params[k] = f"%{kw}%"; keys.append(k)

    def any_ilike(col: str) -> str:
        return "(" + " or ".join(f"{col} ilike :{k}" for k in keys) + ")"

    title_col = "coalesce(title,'')"
    body_col = "coalesce(body,'')"
    sql = f"select id from posts where {any_ilike(title_col)} or {any_ilike(body_col)} order by created_at desc limit :lim"
    rows = (await db.execute(text(sql), params)).mappings().all()
    from app.services import post_service
    out = []
    for r in rows:
        po = await post_service.get(db, r["id"], viewer_id)
        if po:
            out.append(po)
    return out
