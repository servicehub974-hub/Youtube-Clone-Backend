import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyClaim, GemLedger, GemPackage, Order, PaymentSettings, Profile,
    VipSubscription, VipTier, Wallet,
)


class MonetizationError(Exception):
    pass


# ---------- wallet ----------
async def get_balance(db: AsyncSession, user_id: uuid.UUID) -> int:
    r = await db.execute(text("select gems from wallets where user_id = :u::uuid"), {"u": str(user_id)})
    return int(r.scalar_one_or_none() or 0)


async def _credit(db: AsyncSession, user_id: uuid.UUID, delta: int, reason: str, ref: str | None = None):
    """Atomic balance change + ledger row (caller commits)."""
    await db.execute(text("insert into wallets (user_id, gems) values (:u::uuid, 0) on conflict (user_id) do nothing"),
                     {"u": str(user_id)})
    await db.execute(text("update wallets set gems = gems + :d, updated_at = now() where user_id = :u::uuid"),
                     {"u": str(user_id), "d": delta})
    db.add(GemLedger(user_id=user_id, delta=delta, reason=reason, ref=ref))


async def ledger(db: AsyncSession, user_id: uuid.UUID, limit: int = 30):
    rows = (await db.execute(
        select(GemLedger).where(GemLedger.user_id == user_id).order_by(GemLedger.created_at.desc()).limit(limit)
    )).scalars().all()
    return [{"delta": r.delta, "reason": r.reason, "ref": r.ref, "at": r.created_at.isoformat()} for r in rows]


# ---------- VIP ----------
def _tier_dict(t: VipTier) -> dict:
    return {"tier": t.tier, "rank": t.rank, "price_gems": t.price_gems,
            "price_usd": float(t.price_usd) if t.price_usd is not None else None,
            "duration_days": t.duration_days, "daily_gems": t.daily_gems,
            "benefits": list(t.benefits or [])}


async def list_tiers(db: AsyncSession):
    rows = (await db.execute(select(VipTier).where(VipTier.active.is_(True)).order_by(VipTier.rank))).scalars().all()
    return [_tier_dict(t) for t in rows]


async def vip_status(db: AsyncSession, user_id: uuid.UUID):
    row = (await db.execute(text(
        "select tier, expires_at from vip_subscriptions "
        "where user_id = :u::uuid and (expires_at is null or expires_at > now()) "
        "order by expires_at desc nulls first limit 1"
    ), {"u": str(user_id)})).mappings().first()
    if not row:
        return {"active": False, "tier": None, "expires_at": None}
    return {"active": True, "tier": row["tier"],
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None}


async def _activate_vip(db: AsyncSession, user_id: uuid.UUID, tier: VipTier):
    expires = None if tier.duration_days is None else datetime.now(timezone.utc) + timedelta(days=tier.duration_days)
    db.add(VipSubscription(user_id=user_id, tier=tier.tier, expires_at=expires))


async def subscribe_with_gems(db: AsyncSession, user_id: uuid.UUID, tier_name: str):
    tier = (await db.execute(select(VipTier).where(VipTier.tier == tier_name, VipTier.active.is_(True)))).scalar_one_or_none()
    if not tier:
        raise MonetizationError("Unknown tier")
    if tier.price_gems is None:
        raise MonetizationError("This tier is purchased with real money — submit a payment order instead.")
    bal = await get_balance(db, user_id)
    if bal < tier.price_gems:
        raise MonetizationError(f"Not enough Gems. Need {tier.price_gems}, you have {bal}.")
    await _credit(db, user_id, -tier.price_gems, "vip_purchase", tier_name)
    await _activate_vip(db, user_id, tier)
    await db.commit()
    return await vip_status(db, user_id)


# ---------- gem packages ----------
async def list_packages(db: AsyncSession):
    rows = (await db.execute(select(GemPackage).where(GemPackage.active.is_(True)).order_by(GemPackage.sort))).scalars().all()
    return [{"id": str(p.id), "label": p.label, "gems": p.gems, "price_usd": float(p.price_usd)} for p in rows]


# ---------- orders (manual payment) ----------
def _order_dict(o: Order, with_user: bool = False) -> dict:
    d = {"id": str(o.id), "kind": o.kind, "item": o.item, "amount_gems": o.amount_gems,
         "amount_usd": float(o.amount_usd) if o.amount_usd is not None else None,
         "method": o.method, "txn_id": o.txn_id, "status": o.status,
         "created_at": o.created_at.isoformat()}
    if with_user and o.user:
        d["user"] = {"id": str(o.user_id), "name": o.user.display_name or o.user.username or "User"}
    return d


async def create_order(db: AsyncSession, user_id: uuid.UUID, kind: str, item: str, method: str | None, txn_id: str | None):
    amount_gems = None
    amount_usd = None
    if kind == "gems":
        pkg = (await db.execute(select(GemPackage).where(GemPackage.id == uuid.UUID(item)))).scalar_one_or_none()
        if not pkg:
            raise MonetizationError("Unknown gem package")
        amount_gems = pkg.gems
        amount_usd = float(pkg.price_usd)
    elif kind == "vip":
        tier = (await db.execute(select(VipTier).where(VipTier.tier == item))).scalar_one_or_none()
        if not tier:
            raise MonetizationError("Unknown VIP tier")
        amount_usd = float(tier.price_usd) if tier.price_usd is not None else None
    o = Order(user_id=user_id, kind=kind, item=item, amount_gems=amount_gems,
              amount_usd=amount_usd, method=method, txn_id=txn_id, status="pending")
    db.add(o)
    await db.commit()
    return _order_dict(o)


async def list_user_orders(db: AsyncSession, user_id: uuid.UUID):
    rows = (await db.execute(select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(40))).scalars().all()
    return [_order_dict(o) for o in rows]


async def list_orders(db: AsyncSession, status: str | None = "pending"):
    q = select(Order).order_by(Order.created_at.desc()).limit(100)
    if status:
        q = q.where(Order.status == status)
    rows = (await db.execute(q)).scalars().all()
    return [_order_dict(o, with_user=True) for o in rows]


async def approve_order(db: AsyncSession, order_id: uuid.UUID, admin_id: uuid.UUID):
    o = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not o:
        raise MonetizationError("Order not found")
    if o.status == "approved":     # idempotent — never double-credit
        return _order_dict(o)
    if o.status == "rejected":
        raise MonetizationError("Order was already rejected")
    try:
        if o.kind == "gems" and o.amount_gems:
            await _credit(db, o.user_id, o.amount_gems, "gem_purchase", str(o.id))
        elif o.kind == "vip":
            tier = (await db.execute(select(VipTier).where(VipTier.tier == o.item))).scalar_one_or_none()
            if tier:
                await _activate_vip(db, o.user_id, tier)
        o.status = "approved"
        o.decided_at = datetime.now(timezone.utc)
        o.decided_by = admin_id
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise MonetizationError(f"Approve failed: {exc}")
    return _order_dict(o)


async def reject_order(db: AsyncSession, order_id: uuid.UUID, admin_id: uuid.UUID):
    o = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not o:
        raise MonetizationError("Order not found")
    if o.status == "approved":
        raise MonetizationError("Order already approved")
    o.status = "rejected"
    o.decided_at = datetime.now(timezone.utc)
    o.decided_by = admin_id
    await db.commit()
    return _order_dict(o)


# ---------- daily bonus (idempotent per day) ----------
async def claim_daily(db: AsyncSession, user_id: uuid.UUID):
    st = await vip_status(db, user_id)
    if not st["active"]:
        raise MonetizationError("Daily bonus is a VIP perk.")
    tier = (await db.execute(select(VipTier).where(VipTier.tier == st["tier"]))).scalar_one_or_none()
    gems = tier.daily_gems if tier else 0
    if gems <= 0:
        raise MonetizationError("This tier has no daily bonus.")
    today = date.today()
    exists = (await db.execute(text("select 1 from daily_claims where user_id = :u::uuid and day = :d"),
                               {"u": str(user_id), "d": today})).first()
    if exists:
        raise MonetizationError("Already claimed today. Come back tomorrow!")
    db.add(DailyClaim(user_id=user_id, day=today, gems=gems))
    await _credit(db, user_id, gems, "daily_bonus", str(today))
    await db.commit()
    return {"claimed": gems, "balance": await get_balance(db, user_id)}


async def claimed_today(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return (await db.execute(text("select 1 from daily_claims where user_id = :u::uuid and day = :d"),
                             {"u": str(user_id), "d": date.today()})).first() is not None


# ---------- payment settings ----------
async def get_payment_settings(db: AsyncSession):
    row = (await db.execute(select(PaymentSettings).where(PaymentSettings.id == 1))).scalar_one_or_none()
    if not row:
        return {"instructions": "", "pay_number": "", "pay_email": ""}
    return {"instructions": row.instructions or "", "pay_number": row.pay_number or "", "pay_email": row.pay_email or ""}


async def set_payment_settings(db: AsyncSession, instructions: str, number: str, email: str):
    row = (await db.execute(select(PaymentSettings).where(PaymentSettings.id == 1))).scalar_one_or_none()
    if not row:
        row = PaymentSettings(id=1)
        db.add(row)
    row.instructions = instructions
    row.pay_number = number
    row.pay_email = email
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_payment_settings(db)


# ---------- admin: VIP tiers CRUD ----------
def _tier_admin(t: VipTier) -> dict:
    d = _tier_dict(t)
    d["active"] = t.active
    return d


async def admin_list_tiers(db: AsyncSession):
    rows = (await db.execute(select(VipTier).order_by(VipTier.rank))).scalars().all()
    return [_tier_admin(t) for t in rows]


async def upsert_tier(db: AsyncSession, data: dict, key: str | None = None):
    tier_key = key or data.get("tier")
    if not tier_key:
        raise MonetizationError("Tier name required")
    row = (await db.execute(select(VipTier).where(VipTier.tier == tier_key))).scalar_one_or_none()
    if not row:
        row = VipTier(tier=tier_key)
        db.add(row)
    for f in ("rank", "price_gems", "price_usd", "duration_days", "daily_gems", "benefits", "active"):
        if f in data and data[f] is not None:
            setattr(row, f, data[f])
    if "tier" in data and data["tier"] and data["tier"] != tier_key and key is None:
        row.tier = data["tier"]
    await db.commit()
    return _tier_admin((await db.execute(select(VipTier).where(VipTier.tier == (row.tier)))).scalar_one())


async def delete_tier(db: AsyncSession, tier: str):
    row = (await db.execute(select(VipTier).where(VipTier.tier == tier))).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


# ---------- admin: gem packages CRUD ----------
def _pkg_admin(p: GemPackage) -> dict:
    return {"id": str(p.id), "label": p.label, "gems": p.gems, "price_usd": float(p.price_usd), "active": p.active, "sort": p.sort}


async def admin_list_packages(db: AsyncSession):
    rows = (await db.execute(select(GemPackage).order_by(GemPackage.sort))).scalars().all()
    return [_pkg_admin(p) for p in rows]


async def create_package(db: AsyncSession, data: dict):
    p = GemPackage(label=data["label"], gems=data["gems"], price_usd=data["price_usd"],
                   sort=data.get("sort", 0), active=data.get("active", True))
    db.add(p)
    await db.commit()
    return _pkg_admin(p)


async def update_package(db: AsyncSession, pkg_id: uuid.UUID, data: dict):
    p = (await db.execute(select(GemPackage).where(GemPackage.id == pkg_id))).scalar_one_or_none()
    if not p:
        raise MonetizationError("Package not found")
    for f in ("label", "gems", "price_usd", "sort", "active"):
        if f in data and data[f] is not None:
            setattr(p, f, data[f])
    await db.commit()
    return _pkg_admin(p)


async def delete_package(db: AsyncSession, pkg_id: uuid.UUID):
    p = (await db.execute(select(GemPackage).where(GemPackage.id == pkg_id))).scalar_one_or_none()
    if p:
        await db.delete(p)
        await db.commit()
