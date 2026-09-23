-- ============================================================
-- 0008_messaging.sql — conversations, messages, feature flags
-- ============================================================

-- Centralized feature flags (admin toggles)
create table if not exists feature_flags (
  key        text primary key,
  enabled    boolean not null default true,
  updated_at timestamptz not null default now()
);
insert into feature_flags (key, enabled) values ('messages', true)
on conflict (key) do nothing;

-- 1:1 conversations (participants stored ordered to dedupe)
create table if not exists conversations (
  id              uuid primary key default gen_random_uuid(),
  participant_a   uuid not null references profiles(id) on delete cascade,
  participant_b   uuid not null references profiles(id) on delete cascade,
  last_message_at timestamptz,
  created_at      timestamptz not null default now(),
  unique (participant_a, participant_b)
);
create index if not exists idx_conv_a on conversations(participant_a);
create index if not exists idx_conv_b on conversations(participant_b);

create table if not exists messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  sender_id       uuid not null references profiles(id) on delete cascade,
  body            text not null,
  read_at         timestamptz,
  created_at      timestamptz not null default now()
);
create index if not exists idx_messages_conv on messages(conversation_id, created_at);

alter table feature_flags enable row level security;
alter table conversations enable row level security;
alter table messages      enable row level security;
drop policy if exists "features_read" on feature_flags;
create policy "features_read" on feature_flags for select using (true);
