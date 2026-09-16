-- ============================================================
-- 0003_content.sql — Phase 2: content, categories, tags
-- ============================================================

create extension if not exists citext;

-- Categories (up to 3 levels via self-reference) --------------
create table if not exists categories (
  id            uuid primary key default gen_random_uuid(),
  parent_id     uuid references categories(id) on delete set null,
  name          text not null,
  slug          citext not null unique,
  description   text,
  thumbnail_url text,
  cover_url     text,
  position      int not null default 0,
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists idx_categories_parent on categories(parent_id, position);

-- Tags -------------------------------------------------------
create table if not exists tags (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  slug       citext not null unique,
  status     text not null default 'active' check (status in ('active','inactive')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Content ----------------------------------------------------
create table if not exists content (
  id               uuid primary key default gen_random_uuid(),
  owner_id         uuid not null references profiles(id) on delete cascade,
  title            text not null,
  slug             citext not null unique,
  description      text,
  content_type     text not null default 'video'
                     check (content_type in ('video','photo','link')),
  category_id      uuid references categories(id) on delete set null,
  thumbnail_url    text,
  media_url        text,                       -- external URL (or storage key later)
  source           text not null default 'external'
                     check (source in ('external','upload')),
  duration_seconds int,
  visibility       text not null default 'public'
                     check (visibility in ('public','unlisted','private','scheduled')),
  status           text not null default 'published'
                     check (status in ('draft','pending','published','rejected')),
  is_premium       boolean not null default false,
  price_gems       int,
  allow_comments   boolean not null default true,
  views            bigint not null default 0,
  scheduled_at     timestamptz,
  published_at     timestamptz default now(),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
-- Feed cursor index (published_at, id):
create index if not exists idx_content_feed
  on content(published_at desc, id desc)
  where status = 'published' and visibility = 'public';
create index if not exists idx_content_owner    on content(owner_id);
create index if not exists idx_content_category on content(category_id);

-- Content ↔ Tags (many-to-many) ------------------------------
create table if not exists content_tags (
  content_id uuid not null references content(id) on delete cascade,
  tag_id     uuid not null references tags(id) on delete cascade,
  primary key (content_id, tag_id)
);
create index if not exists idx_content_tags_tag on content_tags(tag_id);

-- updated_at triggers ----------------------------------------
drop trigger if exists trg_categories_updated_at on categories;
create trigger trg_categories_updated_at before update on categories
  for each row execute function set_updated_at();
drop trigger if exists trg_tags_updated_at on tags;
create trigger trg_tags_updated_at before update on tags
  for each row execute function set_updated_at();
drop trigger if exists trg_content_updated_at on content;
create trigger trg_content_updated_at before update on content
  for each row execute function set_updated_at();

-- RLS: public read of published content + active taxonomy -----
alter table categories enable row level security;
alter table tags       enable row level security;
alter table content    enable row level security;
alter table content_tags enable row level security;

drop policy if exists "categories_read" on categories;
create policy "categories_read" on categories for select using (true);
drop policy if exists "tags_read" on tags;
create policy "tags_read" on tags for select using (true);
drop policy if exists "content_public_read" on content;
create policy "content_public_read" on content for select
  using (status = 'published' and visibility in ('public','unlisted'));
drop policy if exists "content_tags_read" on content_tags;
create policy "content_tags_read" on content_tags for select using (true);
