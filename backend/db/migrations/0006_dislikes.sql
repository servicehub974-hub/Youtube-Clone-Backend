-- ============================================================
-- 0006_dislikes.sql — dislike reactions (mutually exclusive with likes)
-- ============================================================

create table if not exists dislikes (
  content_id uuid not null references content(id) on delete cascade,
  user_id    uuid not null references profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (content_id, user_id)
);
create index if not exists idx_dislikes_content on dislikes(content_id);
alter table dislikes enable row level security;
