-- ============================================================
-- 0004_social.sql — Phase 5 (part 1): likes + follows
-- ============================================================

create table if not exists likes (
  content_id uuid not null references content(id) on delete cascade,
  user_id    uuid not null references profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (content_id, user_id)
);
create index if not exists idx_likes_content on likes(content_id);

create table if not exists follows (
  follower_id uuid not null references profiles(id) on delete cascade,
  creator_id  uuid not null references profiles(id) on delete cascade,
  created_at  timestamptz not null default now(),
  primary key (follower_id, creator_id),
  check (follower_id <> creator_id)
);
create index if not exists idx_follows_creator on follows(creator_id);

alter table likes   enable row level security;
alter table follows enable row level security;
