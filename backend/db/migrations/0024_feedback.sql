-- ============================================================
-- 0024_feedback.sql — user feedback / support messages
-- ============================================================
create table if not exists feedback (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references profiles(id) on delete set null,
  name       text,
  email      text,
  category   text,
  message    text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_feedback_created on feedback(created_at desc);
alter table feedback enable row level security;
