-- ============================================================
-- 0005_comments.sql — Phase 5: comments, replies, comment likes
-- ============================================================

create table if not exists comments (
  id         uuid primary key default gen_random_uuid(),
  content_id uuid not null references content(id) on delete cascade,
  user_id    uuid not null references profiles(id) on delete cascade,
  parent_id  uuid references comments(id) on delete cascade,  -- null = top-level
  body       text not null,
  is_pinned  boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_comments_content on comments(content_id, parent_id, created_at desc);
create index if not exists idx_comments_parent  on comments(parent_id);

create table if not exists comment_likes (
  comment_id uuid not null references comments(id) on delete cascade,
  user_id    uuid not null references profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (comment_id, user_id)
);

drop trigger if exists trg_comments_updated_at on comments;
create trigger trg_comments_updated_at before update on comments
  for each row execute function set_updated_at();

alter table comments      enable row level security;
alter table comment_likes enable row level security;
drop policy if exists "comments_read" on comments;
create policy "comments_read" on comments for select using (true);
