-- ============================================================
-- 0020_content_unlocks.sql — premium content unlocks (spend Gems)
-- ============================================================
create table if not exists content_unlocks (
  user_id    uuid not null references profiles(id) on delete cascade,
  content_id uuid not null references content(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, content_id)
);
create index if not exists idx_unlocks_user on content_unlocks(user_id, created_at desc);
alter table content_unlocks enable row level security;
