-- ============================================================
-- 0011_anonymous.sql — allow anonymous likes/comments (existing rows safe)
-- Adds a surrogate id PK + nullable user_id + anon_id to reaction tables.
-- ============================================================

-- ---- likes ----
alter table likes add column if not exists id uuid default gen_random_uuid();
alter table likes drop constraint if exists likes_pkey;
alter table likes alter column user_id drop not null;
alter table likes add column if not exists anon_id text;
alter table likes alter column id set not null;
alter table likes add primary key (id);
create unique index if not exists uniq_like_user on likes(content_id, user_id) where user_id is not null;
create unique index if not exists uniq_like_anon on likes(content_id, anon_id) where anon_id is not null;

-- ---- dislikes ----
alter table dislikes add column if not exists id uuid default gen_random_uuid();
alter table dislikes drop constraint if exists dislikes_pkey;
alter table dislikes alter column user_id drop not null;
alter table dislikes add column if not exists anon_id text;
alter table dislikes alter column id set not null;
alter table dislikes add primary key (id);
create unique index if not exists uniq_dislike_user on dislikes(content_id, user_id) where user_id is not null;
create unique index if not exists uniq_dislike_anon on dislikes(content_id, anon_id) where anon_id is not null;

-- ---- comment_likes ----
alter table comment_likes add column if not exists id uuid default gen_random_uuid();
alter table comment_likes drop constraint if exists comment_likes_pkey;
alter table comment_likes alter column user_id drop not null;
alter table comment_likes add column if not exists anon_id text;
alter table comment_likes alter column id set not null;
alter table comment_likes add primary key (id);
create unique index if not exists uniq_clike_user on comment_likes(comment_id, user_id) where user_id is not null;
create unique index if not exists uniq_clike_anon on comment_likes(comment_id, anon_id) where anon_id is not null;

-- ---- comments ----
alter table comments alter column user_id drop not null;
alter table comments add column if not exists anon_id text;
alter table comments add column if not exists anon_name text;

-- ---- feature flags (on by default; admin can disable) ----
insert into feature_flags (key, enabled) values
  ('anonymous_likes', true), ('anonymous_comments', true)
on conflict (key) do nothing;
