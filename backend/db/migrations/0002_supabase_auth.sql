-- ============================================================
-- 0002_supabase_auth.sql — switch to Supabase Auth
-- auth.users (managed by Supabase) is now the canonical user table.
-- Run in Supabase → SQL Editor AFTER enabling Email auth.
-- (Drops the old custom-auth tables — test data only.)
-- ============================================================

drop table if exists sessions cascade;
drop table if exists profiles cascade;
drop table if exists users cascade;

create extension if not exists citext;

-- Roles ------------------------------------------------------
create table if not exists roles (
  id          smallint generated always as identity primary key,
  name        text not null unique,
  created_at  timestamptz not null default now()
);
insert into roles (name) values ('user'), ('creator'), ('admin')
on conflict (name) do nothing;

-- Profiles (1:1 with auth.users) -----------------------------
create table if not exists profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  username      citext unique,
  display_name  text,
  avatar_url    text,
  cover_url     text,
  bio           text,
  location      text,
  website       text,
  role_id       smallint not null default 1 references roles(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists idx_profiles_role on profiles(role_id);

create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists trg_profiles_updated_at on profiles;
create trigger trg_profiles_updated_at before update on profiles
  for each row execute function set_updated_at();

-- Auto-create a profile whenever a new auth user signs up ----
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  uname text;
begin
  uname := coalesce(
    nullif(new.raw_user_meta_data->>'username', ''),
    split_part(new.email, '@', 1) || '-' || substr(replace(new.id::text, '-', ''), 1, 5)
  );
  insert into public.profiles (id, username, display_name)
  values (
    new.id,
    uname,
    coalesce(nullif(new.raw_user_meta_data->>'display_name', ''), split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- RLS: profiles publicly readable; all writes go through FastAPI backend
alter table profiles enable row level security;
drop policy if exists "profiles_public_read" on profiles;
create policy "profiles_public_read" on profiles for select using (true);
alter table roles enable row level security;

-- ============================================================
-- SEED YOUR FIRST ADMIN (run once, after you've signed up):
--   update profiles set role_id = (select id from roles where name = 'admin')
--   where id = (select id from auth.users where email = 'YOUR_EMAIL_HERE');
-- ============================================================
