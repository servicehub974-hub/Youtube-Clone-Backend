-- ============================================================
-- 0027_settings_reviews.sql — login history + platform reviews
-- ============================================================
create table if not exists login_events (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  ip         text,
  user_agent text,
  created_at timestamptz not null default now()
);
create index if not exists idx_login_events_user on login_events(user_id, created_at desc);

create table if not exists reviews (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  rating     int not null default 5,
  body       text,
  created_at timestamptz not null default now(),
  unique (user_id)
);
create index if not exists idx_reviews_created on reviews(created_at desc);

alter table login_events enable row level security;
alter table reviews enable row level security;
drop policy if exists "reviews_read" on reviews;
create policy "reviews_read" on reviews for select using (true);
