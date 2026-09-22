-- ============================================================
-- 0023_notif_actor.sql — actor avatar on notifications + VIP expiry flag
-- ============================================================
alter table notifications add column if not exists actor_avatar text;
alter table vip_subscriptions add column if not exists expiry_notified boolean not null default false;
