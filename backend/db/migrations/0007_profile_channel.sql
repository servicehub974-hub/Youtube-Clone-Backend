-- ============================================================
-- 0007_profile_channel.sql — shorts auto-detect + profile links
-- ============================================================

alter table content add column if not exists is_short boolean not null default false;
create index if not exists idx_content_short on content(is_short);

alter table profiles add column if not exists links jsonb not null default '[]'::jsonb;
-- cover_url already exists (from 0002); nothing to add for the banner.
