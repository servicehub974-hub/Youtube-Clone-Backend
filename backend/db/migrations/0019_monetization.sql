-- ============================================================
-- 0019_monetization.sql — Gems wallet, VIP tiers, orders, daily bonus
-- ============================================================
create table if not exists wallets (
  user_id    uuid primary key references profiles(id) on delete cascade,
  gems       bigint not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists gem_ledger (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  delta      bigint not null,
  reason     text not null,
  ref        text,
  created_at timestamptz not null default now()
);
create index if not exists idx_ledger_user on gem_ledger(user_id, created_at desc);

create table if not exists vip_tiers (
  tier          text primary key,
  rank          int not null default 0,
  price_gems    bigint,
  price_usd     numeric(10,2),
  duration_days int,                       -- null = lifetime
  daily_gems    int not null default 0,
  benefits      jsonb not null default '[]',
  active        boolean not null default true
);

create table if not exists vip_subscriptions (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  tier       text not null,
  started_at timestamptz not null default now(),
  expires_at timestamptz,                  -- null = lifetime
  created_at timestamptz not null default now()
);
create index if not exists idx_vip_user on vip_subscriptions(user_id, expires_at desc);

create table if not exists gem_packages (
  id        uuid primary key default gen_random_uuid(),
  label     text not null,
  gems      bigint not null,
  price_usd numeric(10,2) not null,
  active    boolean not null default true,
  sort      int not null default 0
);

create table if not exists orders (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references profiles(id) on delete cascade,
  kind        text not null,               -- vip / gems / shop
  item        text not null,               -- tier name / package id / product id
  amount_gems bigint,
  amount_usd  numeric(10,2),
  method      text,
  txn_id      text,
  status      text not null default 'pending',   -- pending / approved / rejected
  note        text,
  created_at  timestamptz not null default now(),
  decided_at  timestamptz,
  decided_by  uuid references profiles(id)
);
create index if not exists idx_orders_status on orders(status, created_at desc);
create index if not exists idx_orders_user on orders(user_id, created_at desc);

create table if not exists payment_settings (
  id           int primary key default 1,
  instructions text,
  pay_number   text,
  pay_email    text,
  updated_at   timestamptz not null default now()
);
insert into payment_settings (id, instructions)
  values (1, 'Send the payment to the number/email below, then submit your Transaction/Order ID. An admin will approve it shortly.')
  on conflict (id) do nothing;

create table if not exists daily_claims (
  user_id    uuid not null references profiles(id) on delete cascade,
  day        date not null,
  gems       int not null,
  created_at timestamptz not null default now(),
  primary key (user_id, day)
);

-- seed default VIP tiers (admin-configurable afterwards)
insert into vip_tiers (tier, rank, price_gems, duration_days, daily_gems, benefits) values
  ('silver', 1, 500, 30, 10, '["No ads","Custom badge","+10 Gems/day"]'::jsonb),
  ('gold', 2, 1000, 30, 25, '["No ads","Exclusive content","Priority support","Custom badge","+25 Gems/day"]'::jsonb),
  ('platinum', 3, 2500, 30, 50, '["No ads","Exclusive content","Priority support","Early access","Custom badge","+50 Gems/day"]'::jsonb)
on conflict (tier) do nothing;
insert into vip_tiers (tier, rank, price_usd, duration_days, daily_gems, benefits) values
  ('lifetime', 4, 199.90, null, 50, '["Everything in Platinum","Lifetime access","Founder badge"]'::jsonb)
on conflict (tier) do nothing;

-- seed a few gem packages
insert into gem_packages (label, gems, price_usd, sort)
select * from (values
  ('Starter · 500 Gems', 500, 4.99, 1),
  ('Popular · 1200 Gems', 1200, 9.99, 2),
  ('Pro · 3000 Gems', 3000, 19.99, 3),
  ('Whale · 8000 Gems', 8000, 49.99, 4)
) as v(label, gems, price_usd, sort)
where not exists (select 1 from gem_packages);

alter table wallets enable row level security;
alter table gem_ledger enable row level security;
alter table vip_tiers enable row level security;
alter table vip_subscriptions enable row level security;
alter table gem_packages enable row level security;
alter table orders enable row level security;
alter table payment_settings enable row level security;
alter table daily_claims enable row level security;
drop policy if exists "vip_tiers_read" on vip_tiers;
create policy "vip_tiers_read" on vip_tiers for select using (true);
drop policy if exists "gem_packages_read" on gem_packages;
create policy "gem_packages_read" on gem_packages for select using (active);
drop policy if exists "payment_settings_read" on payment_settings;
create policy "payment_settings_read" on payment_settings for select using (true);
