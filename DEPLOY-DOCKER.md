# NEXUS — Docker / VPS deploy (Phase 12)

Run the whole stack (frontend + backend + redis) on any VPS with Docker.

## 1. Install Docker
```
curl -fsSL https://get.docker.com | sh
```

## 2. Env files
- `backend/.env` — same vars you set on Render (DATABASE_URL, SUPABASE_URL,
  SUPABASE_JWT_SECRET, CORS_ORIGINS, storage vars, REDIS_URL=redis://redis:6379, …)
- `frontend/.env` — NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SITE_URL
- A root `.env` with the same NEXT_PUBLIC_* values (compose passes them as build
  args, because Next bakes them at build time).

## 3. Build + run
```
docker compose up -d --build
```
- backend → http://SERVER_IP:8000
- frontend → http://SERVER_IP:3000

## 4. Put Nginx / Cloudflare in front (TLS)
Point your domain at the VPS, proxy 443 → frontend:3000 and `/api` → backend:8000,
or run each on its own subdomain. Set `CORS_ORIGINS` to your real frontend URL.

## 5. Redis
Already included. Set `REDIS_URL=redis://redis:6379` in `backend/.env` to use it
(caching / view-dedup / rate-limit) instead of the in-memory fallback.

## Updating
```
git pull && docker compose up -d --build
```
Migrations still run in Supabase's SQL editor (DB is unchanged by Docker).
