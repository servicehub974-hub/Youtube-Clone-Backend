# NEXUS Backend (FastAPI)

## Run locally

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload --port 8000
```

- API root: http://localhost:8000
- Health:   http://localhost:8000/api/health
- Docs:     http://localhost:8000/docs

## Structure

```
backend/
  requirements.txt
  .env.example
  app/
    main.py            # FastAPI app + CORS + router mount
    core/
      config.py        # settings from env
    api/
      router.py        # aggregates all route modules
      routes/
        health.py      # /api/health
```

New feature routers (auth, content, search, gems…) get added under
`app/api/routes/` and registered in `app/api/router.py`.
