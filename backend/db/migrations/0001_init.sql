-- ============================================================
-- 0001_init.sql  —  Phase 1 foundation schema
-- Run this in Supabase → SQL Editor (or via Supabase CLI).
-- Safe to re-run: uses IF NOT EXISTS / idempotent guards.
-- ============================================================

-- Extensions ------------------------------------------------
create extension if not exists citext;      -- case-insensitive email/username

-- updated_at helper -----------------------------------------
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Roles -----------------------------------------------------
create table if not exists roles (
  id          smallint generated always as identity primary key,
  name        text not null unique,          -- 'user' | 'creator' | 'admin'
  created_at  timestamptz not null default now()
);

insert into roles (name) values ('user'), ('creator'), ('admin')
on conflict (name) do nothing;

-- Users -----------------------------------------------------
create table if not exists users (
  id                 uuid primary key default gen_random_uuid(),
  email              citext not null unique,
  username           citext not null unique,
  password_hash      text,                    -- null until set (admin-created / social later)
  display_name       text,
  role_id            smallint not null default 1 references roles(id),
  status             text not null default 'active'
                       check (status in ('active','suspended','banned')),
  email_verified     boolean not null default false,
  -- ownership model: who actually created the record (admin/self)
  created_by_user_id uuid references users(id) on delete set null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index if not exists idx_users_role       on users(role_id);
create index if not exists idx_users_status      on users(status);
create index if not exists idx_users_created_at  on users(created_at, id);

drop trigger if exists trg_users_updated_at on users;
create trigger trg_users_updated_at before update on users
  for each row execute function set_updated_at();

-- Profiles (1:1 with users) ---------------------------------
create table if not exists profiles (
  user_id     uuid primary key references users(id) on delete cascade,
  avatar_url  text,
  cover_url   text,
  bio         text,
  location    text,
  website     text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

drop trigger if exists trg_profiles_updated_at on profiles;
create trigger trg_profiles_updated_at before update on profiles
  for each row execute function set_updated_at();

-- Sessions (refresh tokens) ---------------------------------
create table if not exists sessions (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references users(id) on delete cascade,
  refresh_token_hash  text not null,          -- store a hash, never the raw token
  user_agent          text,
  ip                  inet,
  expires_at          timestamptz not null,
  revoked_at          timestamptz,
  created_at          timestamptz not null default now()
);

create index if not exists idx_sessions_user       on sessions(user_id);
create index if not exists idx_sessions_expires_at on sessions(expires_at);

-- Row Level Security ----------------------------------------
-- The FastAPI backend connects with a privileged Postgres role and enforces
-- authorization in the app layer. RLS is enabled with NO permissive policies
-- so that the anon/PostgREST API cannot read these tables directly.
alter table users    enable row level security;
alter table profiles enable row level security;
alter table sessions enable row level security;
alter table roles    enable row level security;
