-- ============================================================
-- 0016_search.sql — search history (recent / trending / zero-result)
-- ============================================================
create table if not exists search_history (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid references profiles(id) on delete cascade,
  anon_id       text,
  query         text not null,
  results_count int not null default 0,
  created_at    timestamptz not null default now()
);
create index if not exists idx_search_user on search_history(user_id, created_at desc);
create index if not exists idx_search_recent on search_history(created_at desc);
alter table search_history enable row level security;

-- trigram search speedups (optional but recommended)
create extension if not exists pg_trgm;
create index if not exists idx_content_title_trgm on content using gin (title gin_trgm_ops);
