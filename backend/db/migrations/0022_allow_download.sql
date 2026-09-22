-- ============================================================
-- 0022_allow_download.sql — per-content download permission
-- ============================================================
alter table content add column if not exists allow_download boolean not null default false;
