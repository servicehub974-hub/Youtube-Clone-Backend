import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.db import get_db
from app.models import Profile
from app.services import monetization_service as mon
from app.services.monetization_service import MonetizationError

router = APIRouter()


class SubscribeIn(BaseModel):
    tier: str


class OrderIn(BaseModel):
    kind: str          # vip / gems / shop
    item: str          # tier name / package id
    method: str | None = None
    txn_id: str | None = None


class PaymentSettingsIn(BaseModel):
    instructions: str = ""
    pay_number: str = ""
    pay_email: str = ""


# ---------- public / user ----------
@router.get("/vip/tiers")
async def vip_tiers(db: AsyncSession = Depends(get_db)):
    return await mon.list_tiers(db)


@router.get("/gems/packages")
async def gem_packages(db: AsyncSession = Depends(get_db)):
    return await mon.list_packages(db)


@router.get("/payment/settings")
async def payment_settings(db: AsyncSession = Depends(get_db)):
    return await mon.get_payment_settings(db)


@router.get("/vip/me")
async def my_vip(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await mon.vip_status(db, user.id)


@router.get("/wallet")
async def my_wallet(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {
        "gems": await mon.get_balance(db, user.id),
        "ledger": await mon.ledger(db, user.id),
        "claimed_today": await mon.claimed_today(db, user.id),
    }


@router.post("/wallet/daily-bonus")
async def daily_bonus(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await mon.claim_daily(db, user.id)
    except MonetizationError as e:
        raise HTTPException(400, detail=str(e))


@router.post("/vip/subscribe")
async def subscribe(data: SubscribeIn, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await mon.subscribe_with_gems(db, user.id, data.tier)
    except MonetizationError as e:
        raise HTTPException(400, detail=str(e))


@router.post("/orders")
async def create_order(data: OrderIn, user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await mon.create_order(db, user.id, data.kind, data.item, data.method, data.txn_id)
    except MonetizationError as e:
        raise HTTPException(400, detail=str(e))


@router.get("/orders/me")
async def my_orders(user: Profile = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await mon.list_user_orders(db, user.id)


# ---------- admin ----------
@router.get("/admin/orders")
async def admin_orders(status: str = "pending", admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await mon.list_orders(db, status or None)


@router.post("/admin/orders/{order_id}/approve")
async def admin_approve(order_id: str, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    try:
        return await mon.approve_order(db, uuid.UUID(order_id), admin.id)
    except MonetizationError as e:
        raise HTTPException(400, detail=str(e))


@router.post("/admin/orders/{order_id}/reject")
async def admin_reject(order_id: str, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    try:
        return await mon.reject_order(db, uuid.UUID(order_id), admin.id)
    except MonetizationError as e:
        raise HTTPException(400, detail=str(e))


@router.put("/admin/payment-settings")
async def admin_payment_settings(data: PaymentSettingsIn, admin: Profile = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await mon.set_payment_settings(db, data.instructions, data.pay_number, data.pay_email)
