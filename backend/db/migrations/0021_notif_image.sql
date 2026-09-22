-- ============================================================
-- 0021_notif_image.sql — notification thumbnail/image
-- ============================================================
alter table notifications add column if not exists image text;
