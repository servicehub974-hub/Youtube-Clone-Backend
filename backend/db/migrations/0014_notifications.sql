-- ============================================================
-- 0014_notifications.sql — notifications
-- ============================================================
create table if not exists notifications (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,  -- recipient
  type       text not null,
  actor_name text,
  message    text not null,
  link       text,
  is_read    boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists idx_notif_user on notifications(user_id, created_at desc);
create index if not exists idx_notif_unread on notifications(user_id) where is_read = false;
alter table notifications enable row level security;
