-- ============================================================
-- 0009_realtime.sql — Supabase Realtime for messages + read RLS
-- (Backend uses a privileged connection and bypasses RLS; these
--  policies are so the authenticated browser client can receive
--  its own rows via Realtime.)
-- ============================================================

-- Read policies keyed to the logged-in Supabase user (auth.uid())
drop policy if exists "conversations_read" on conversations;
create policy "conversations_read" on conversations for select
  using (participant_a = auth.uid() or participant_b = auth.uid());

drop policy if exists "messages_read" on messages;
create policy "messages_read" on messages for select using (
  exists (
    select 1 from conversations c
    where c.id = messages.conversation_id
      and (c.participant_a = auth.uid() or c.participant_b = auth.uid())
  )
);

-- Add tables to the Realtime publication (idempotent)
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and tablename = 'messages'
  ) then
    alter publication supabase_realtime add table messages;
  end if;
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and tablename = 'conversations'
  ) then
    alter publication supabase_realtime add table conversations;
  end if;
end $$;
