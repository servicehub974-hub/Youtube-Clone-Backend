-- ============================================================
-- 0010_realtime_engagement.sql — realtime for comments/likes
-- ============================================================

-- public read policies so the browser client can receive realtime rows
drop policy if exists "likes_read" on likes;
create policy "likes_read" on likes for select using (true);
drop policy if exists "dislikes_read" on dislikes;
create policy "dislikes_read" on dislikes for select using (true);
drop policy if exists "comment_likes_read" on comment_likes;
create policy "comment_likes_read" on comment_likes for select using (true);
-- comments already have a public read policy (0005)

do $$
declare t text;
begin
  foreach t in array array['comments','comment_likes','likes','dislikes'] loop
    if not exists (
      select 1 from pg_publication_tables
      where pubname = 'supabase_realtime' and tablename = t
    ) then
      execute format('alter publication supabase_realtime add table %I', t);
    end if;
  end loop;
end $$;
