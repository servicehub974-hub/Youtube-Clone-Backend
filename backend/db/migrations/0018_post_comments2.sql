-- ============================================================
-- 0018_post_comments2.sql — post comment replies + likes
-- ============================================================
alter table post_comments add column if not exists parent_id uuid references post_comments(id) on delete cascade;
create index if not exists idx_post_comments_parent on post_comments(parent_id);

create table if not exists post_comment_likes (
  comment_id uuid not null references post_comments(id) on delete cascade,
  user_id    uuid not null references profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (comment_id, user_id)
);
alter table post_comment_likes enable row level security;
