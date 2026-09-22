-- ============================================================
-- 0017_posts.sql — Facebook-style posts / feed
-- ============================================================
create table if not exists posts (
  id         uuid primary key default gen_random_uuid(),
  author_id  uuid not null references profiles(id) on delete cascade,
  title      text,
  body       text,
  video_url  text,
  images     jsonb not null default '[]',
  repost_of  uuid references posts(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_posts_created on posts(created_at desc);
create index if not exists idx_posts_author  on posts(author_id, created_at desc);

create table if not exists post_likes (
  post_id uuid not null references posts(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);
create table if not exists post_saves (
  post_id uuid not null references posts(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);
create table if not exists post_comments (
  id         uuid primary key default gen_random_uuid(),
  post_id    uuid not null references posts(id) on delete cascade,
  author_id  uuid not null references profiles(id) on delete cascade,
  body       text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_post_comments on post_comments(post_id, created_at);

drop trigger if exists trg_posts_updated_at on posts;
create trigger trg_posts_updated_at before update on posts
  for each row execute function set_updated_at();

alter table posts enable row level security;
alter table post_likes enable row level security;
alter table post_saves enable row level security;
alter table post_comments enable row level security;
drop policy if exists "posts_read" on posts;
create policy "posts_read" on posts for select using (true);
drop policy if exists "post_comments_read" on post_comments;
create policy "post_comments_read" on post_comments for select using (true);
