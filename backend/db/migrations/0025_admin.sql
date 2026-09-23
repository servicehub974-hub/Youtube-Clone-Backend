-- ============================================================
-- 0025_admin.sql — moderation, reports, audit log, site branding
-- ============================================================
alter table profiles add column if not exists banned boolean not null default false;

create table if not exists reports (
  id          uuid primary key default gen_random_uuid(),
  reporter_id uuid references profiles(id) on delete set null,
  target_type text not null,             -- content / comment / post / user
  target_id   uuid not null,
  reason      text,
  status      text not null default 'open',   -- open / resolved / dismissed
  created_at  timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by uuid references profiles(id)
);
create index if not exists idx_reports_status on reports(status, created_at desc);

create table if not exists audit_log (
  id         uuid primary key default gen_random_uuid(),
  admin_id   uuid references profiles(id) on delete set null,
  admin_name text,
  action     text not null,
  detail     text,
  created_at timestamptz not null default now()
);
create index if not exists idx_audit_created on audit_log(created_at desc);

create table if not exists site_settings (
  id          int primary key default 1,
  name        text not null default 'NEXUS PRO',
  logo_url    text,
  favicon_url text,
  tagline     text
);
insert into site_settings (id, name, tagline) values (1, 'NEXUS PRO', 'Premium content universe')
  on conflict (id) do nothing;

alter table reports enable row level security;
alter table audit_log enable row level security;
alter table site_settings enable row level security;
drop policy if exists "site_read" on site_settings;
create policy "site_read" on site_settings for select using (true);
