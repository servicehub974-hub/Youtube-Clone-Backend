-- ============================================================
-- 0012_saves.sql — saved content (personal library)
-- ============================================================
create table if not exists saves (
  user_id    uuid not null references profiles(id) on delete cascade,
  content_id uuid not null references content(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, content_id)
);
create index if not exists idx_saves_user on saves(user_id, created_at desc);
alter table saves enable row level security;
