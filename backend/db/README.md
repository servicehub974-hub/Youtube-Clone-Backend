# Database migrations

Plain SQL migrations for the Supabase Postgres database. Run them in order.

## How to apply

**Option A — Supabase SQL Editor (easiest):**
1. Open your Supabase project → **SQL Editor**.
2. Paste the contents of each file in `migrations/` in order (`0001_...`, then
   `0002_...`, etc.) and run.

**Option B — psql / Supabase CLI:**
```bash
psql "$DATABASE_URL" -f db/migrations/0001_init.sql
```

## Order
- `0001_init.sql` — roles, users, profiles, sessions + indexes + RLS (Phase 1).

Later phases append new numbered files here (content, tags, gems, etc.).
Do not edit an already-applied migration — add a new one.
