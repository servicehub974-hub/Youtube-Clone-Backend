-- ============================================================
-- 0015_playlists.sql — playlists + items (many-to-many)
-- ============================================================
create table if not exists playlists (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references profiles(id) on delete cascade,
  title       text not null,
  description text,
  visibility  text not null default 'public'
                check (visibility in ('public','unlisted','private')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists idx_playlists_owner on playlists(owner_id, updated_at desc);

create table if not exists playlist_items (
  playlist_id uuid not null references playlists(id) on delete cascade,
  content_id  uuid not null references content(id) on delete cascade,
  position    int  not null default 0,
  added_at    timestamptz not null default now(),
  primary key (playlist_id, content_id)
);
create index if not exists idx_playlist_items on playlist_items(playlist_id, position);

drop trigger if exists trg_playlists_updated_at on playlists;
create trigger trg_playlists_updated_at before update on playlists
  for each row execute function set_updated_at();

alter table playlists enable row level security;
alter table playlist_items enable row level security;
drop policy if exists "playlists_read" on playlists;
create policy "playlists_read" on playlists for select using (visibility in ('public','unlisted'));
drop policy if exists "playlist_items_read" on playlist_items;
create policy "playlist_items_read" on playlist_items for select using (true);
