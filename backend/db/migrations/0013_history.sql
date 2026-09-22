-- ============================================================
-- 0013_history.sql — watch history (Timeline)
-- ============================================================
create table if not exists watch_history (
  user_id    uuid not null references profiles(id) on delete cascade,
  content_id uuid not null references content(id) on delete cascade,
  watched_at timestamptz not null default now(),
  primary key (user_id, content_id)
);
create index if not exists idx_history_user on watch_history(user_id, watched_at desc);
alter table watch_history enable row level security;
