# NEXUS — Premium Digital Content Platform

Full-stack marketplace + creator + social platform. Built phase by phase — see
[`PROGRESS.md`](./PROGRESS.md).

**Stack:** Next.js + TypeScript (frontend) · FastAPI + Python (backend) ·
Supabase Postgres · Redis · object storage (B2/R2) · Cloudflare CDN · FFmpeg worker.

```
.
├── frontend/     # Next.js app (App Router, Tailwind, React Query)
├── backend/      # FastAPI app (modular, async)
├── render.yaml   # one-push deploy blueprint for Render
└── PROGRESS.md   # phase-by-phase build tracker
```

## Run locally

**Backend** (terminal 1):
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Frontend** (terminal 2):
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000 — you should see the dark theme **and** a green
"API online" chip at the top, confirming the frontend is talking to the backend.
If the chip is red, the backend isn't running or `NEXT_PUBLIC_API_URL` is wrong.

## Deploy (GitHub → Render)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, connect the repo (it reads `render.yaml`).
3. After both services deploy, set the two env vars:
   - `nexus-frontend` → `NEXT_PUBLIC_API_URL` = your `nexus-api` URL
   - `nexus-api` → `CORS_ORIGINS` = your `nexus-frontend` URL
4. Redeploy. The health chip should go green in production too.

> Frontend can also go on Vercel if you prefer — just set `NEXT_PUBLIC_API_URL`
> there and add the Vercel URL to the backend `CORS_ORIGINS`.
