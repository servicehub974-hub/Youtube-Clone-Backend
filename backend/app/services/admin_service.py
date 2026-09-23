import uuid

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog, Comment, Content, Message, Post, Profile, Report, SiteSettings, Wallet,
)


async def audit(db: AsyncSession, admin: Profile, action: str, detail: str = ""):
    """Best-effort audit — never breaks the caller (own commit, swallows errors
    e.g. if the audit_log table isn't migrated yet)."""
    try:
        db.add(AuditLog(admin_id=admin.id, admin_name=(admin.display_name or admin.username or "admin"),
                        action=action, detail=detail))
        await db.commit()
    except Exception:
        await db.rollback()


async def list_audit(db: AsyncSession, limit: int = 100):
    rows = (await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))).scalars().all()
    return [{"admin": a.admin_name or "admin", "action": a.action, "detail": a.detail,
             "at": a.created_at.isoformat() if a.created_at else None} for a in rows]


# ---------- users ----------
async def ban_user(db: AsyncSession, admin: Profile, user_id: uuid.UUID, banned: bool):
    await db.execute(update(Profile).where(Profile.id == user_id).values(banned=banned))
    await db.commit()
    await audit(db, admin, "ban" if banned else "unban", f"user={user_id}")
    return {"ok": True, "banned": banned}


# ---------- reports ----------
async def create_report(db: AsyncSession, reporter_id, target_type: str, target_id: uuid.UUID, reason: str | None):
    db.add(Report(reporter_id=reporter_id, target_type=target_type, target_id=target_id, reason=reason))
    await db.commit()
    return {"ok": True}


async def list_reports(db: AsyncSession, status: str = "open"):
    q = select(Report).order_by(Report.created_at.desc()).limit(200)
    if status:
        q = q.where(Report.status == status)
    rows = (await db.execute(q)).scalars().all()
    out = []
    for r in rows:
        preview = None
        link = None
        try:
            if r.target_type == "content":
                c = (await db.execute(select(Content.title, Content.thumbnail_url).where(Content.id == r.target_id))).first()
                preview = {"title": c[0], "thumbnail": c[1]} if c else None
                link = f"/content/{r.target_id}"
            elif r.target_type == "comment":
                c = (await db.execute(select(Comment.body, Comment.content_id).where(Comment.id == r.target_id))).first()
                preview = {"title": (c[0][:80] if c else "(deleted)")} if c else None
                link = f"/content/{c[1]}" if c and c[1] else None
            elif r.target_type == "post":
                c = (await db.execute(select(Post.title, Post.body).where(Post.id == r.target_id))).first()
                preview = {"title": (c[0] or (c[1][:80] if c[1] else "Post")) if c else "(deleted)"}
                link = f"/post/{r.target_id}"
            elif r.target_type == "message":
                c = (await db.execute(select(Message.body).where(Message.id == r.target_id))).first()
                preview = {"title": (c[0][:80] if c else "(deleted)")} if c else None
            elif r.target_type == "user":
                c = (await db.execute(select(Profile.display_name, Profile.username, Profile.avatar_url).where(Profile.id == r.target_id))).first()
                preview = {"title": (c[0] or c[1] or "User"), "thumbnail": c[2]} if c else None
                link = f"/channel/{r.target_id}"
        except Exception:
            preview = None
        out.append({"id": str(r.id), "target_type": r.target_type, "target_id": str(r.target_id),
                    "reason": r.reason, "preview": preview, "link": link,
                    "created_at": r.created_at.isoformat() if r.created_at else None})
    return out


async def resolve_report(db: AsyncSession, admin: Profile, report_id: uuid.UUID, dismiss: bool = True):
    r = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not r:
        return {"ok": False}
    r.status = "dismissed" if dismiss else "resolved"
    r.resolved_by = admin.id
    from datetime import datetime, timezone
    r.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await audit(db, admin, "report_dismiss" if dismiss else "report_resolve", f"report={report_id}")
    return {"ok": True}


async def takedown(db: AsyncSession, admin: Profile, report_id: uuid.UUID):
    r = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not r:
        return {"ok": False}
    owner_id = None
    ctitle = cthumb = None
    cid = None
    if r.target_type == "content":
        c = (await db.execute(select(Content).where(Content.id == r.target_id))).scalar_one_or_none()
        if c:
            c.status = "removed"; c.visibility = "private"
            owner_id, ctitle, cthumb, cid = c.owner_id, c.title, c.thumbnail_url, c.id
    elif r.target_type == "comment":
        c = (await db.execute(select(Comment).where(Comment.id == r.target_id))).scalar_one_or_none()
        if c:
            await db.delete(c)
    elif r.target_type == "post":
        p = (await db.execute(select(Post).where(Post.id == r.target_id))).scalar_one_or_none()
        if p:
            await db.delete(p)
    elif r.target_type == "message":
        m = (await db.execute(select(Message).where(Message.id == r.target_id))).scalar_one_or_none()
        if m:
            await db.delete(m)
    elif r.target_type == "user":
        await db.execute(update(Profile).where(Profile.id == r.target_id).values(banned=True))

    r.status = "resolved"
    r.resolved_by = admin.id
    from datetime import datetime, timezone
    r.resolved_at = datetime.now(timezone.utc)
    # CORE commit — must succeed with existing columns only
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        return {"ok": False}

    # best-effort owner notification (separate txn; never breaks takedown)
    if owner_id:
        try:
            from app.services import notification_service
            notification_service.add(db, owner_id, "moderation", "Moderator", f'Your content "{ctitle}" was hidden after a report', f"/content/{cid}", cthumb)
            await db.commit()
        except Exception:
            await db.rollback()
    await audit(db, admin, "takedown", f"{r.target_type}={r.target_id}")
    return {"ok": True}


# ---------- analytics ----------
async def analytics(db: AsyncSession):
    async def one(sql: str) -> int:
        try:
            return int((await db.execute(text(sql))).scalar() or 0)
        except Exception:
            return 0
    return {
        "users": await one("select count(*) from profiles"),
        "creators": await one("select count(*) from profiles p join roles r on r.id=p.role_id where r.name in ('creator','admin')"),
        "content": await one("select count(*) from content"),
        "posts": await one("select count(*) from posts"),
        "comments": await one("select count(*) from comments"),
        "likes": await one("select count(*) from likes"),
        "views": await one("select coalesce(sum(views),0) from content"),
        "gems_in_circulation": await one("select coalesce(sum(gems),0) from wallets"),
        "orders_pending": await one("select count(*) from orders where status='pending'"),
        "reports_open": await one("select count(*) from reports where status='open'"),
        "vip_active": await one("select count(*) from vip_subscriptions where expires_at is null or expires_at > now()"),
    }


# ---------- site branding ----------
async def get_site(db: AsyncSession):
    row = (await db.execute(select(SiteSettings).where(SiteSettings.id == 1))).scalar_one_or_none()
    if not row:
        return {"name": "NEXUS PRO", "logo_url": None, "favicon_url": None, "tagline": None}
    return {"name": row.name, "logo_url": row.logo_url, "favicon_url": row.favicon_url, "tagline": row.tagline}


async def set_site(db: AsyncSession, admin: Profile, name: str, logo_url: str | None, favicon_url: str | None, tagline: str | None):
    row = (await db.execute(select(SiteSettings).where(SiteSettings.id == 1))).scalar_one_or_none()
    if not row:
        row = SiteSettings(id=1)
        db.add(row)
    row.name = name or "NEXUS PRO"
    row.logo_url = logo_url or None
    row.favicon_url = favicon_url or None
    row.tagline = tagline or None
    await db.commit()
    await audit(db, admin, "site_update", name)
    return await get_site(db)


async def restore_content(db: AsyncSession, admin: Profile, content_id: uuid.UUID):
    c = (await db.execute(select(Content).where(Content.id == content_id))).scalar_one_or_none()
    if not c:
        return {"ok": False}
    c.status = "published"
    c.visibility = "public"
    owner_id, ctitle, cthumb = c.owner_id, c.title, c.thumbnail_url
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        return {"ok": False}
    try:
        from app.services import notification_service
        notification_service.add(db, owner_id, "moderation", "Moderator", f'Your content "{ctitle}" was restored', f"/content/{content_id}", cthumb)
        await db.commit()
    except Exception:
        await db.rollback()
    await audit(db, admin, "restore", f"content={content_id}")
    return {"ok": True}


async def hidden_content(db: AsyncSession, limit: int = 100):
    rows = (await db.execute(select(Content).where(Content.status == "removed").order_by(Content.created_at.desc()).limit(limit))).scalars().all()
    return [{"id": str(c.id), "title": c.title, "thumbnail": c.thumbnail_url,
             "content_type": c.content_type, "is_short": c.is_short} for c in rows]
