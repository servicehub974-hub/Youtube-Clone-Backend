-- ============================================================
-- 0026_blocks.sql — user blocking
-- ============================================================
create table if not exists user_blocks (
  blocker_id uuid not null references profiles(id) on delete cascade,
  blocked_id uuid not null references profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker_id, blocked_id)
);
alter table user_blocks enable row level security;
