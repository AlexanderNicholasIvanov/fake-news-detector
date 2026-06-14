# Fake-News Detector

Automated pipeline that polls curated RSS feeds, fetches full article text,
scores each article for **credibility** with a **local LLM** (Ollama + `qwen3:14b`),
stores results in Postgres, and surfaces them in a React dashboard.

See [`PLAN.md`](./PLAN.md) for the full design and milestone breakdown.

**Status: M0 (scaffold & infra).** The skeleton runs end-to-end — Postgres +
Alembic, a FastAPI read API, and a Vite/React/Tailwind dashboard — but ingestion
(M1) and scoring (M2) are not wired yet, so the feed is empty.

## Prerequisites

- Docker + Docker Compose
- (For running outside Docker) Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22+
- (M2) [Ollama](https://ollama.com) on the host with `ollama pull qwen3:14b`

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Then:

- Dashboard → http://localhost:5173  (shows "No articles yet" — expected at M0)
- API health → http://localhost:8000/health  → `{"status":"ok"}`
- API docs → http://localhost:8000/docs

## Running the backend locally (without Docker)

```bash
cd backend
uv sync
# Point DATABASE_URL at a local Postgres, then:
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest
```

## Running the frontend locally

```bash
cd frontend
npm install
npm run dev
```

## Layout

```
backend/   FastAPI app, SQLAlchemy models, Alembic migrations, config/, tests/
frontend/  Vite + React + TypeScript + Tailwind dashboard
docker-compose.yml   db + api + frontend (worker added in M1)
PLAN.md    Full implementation plan and milestones
```

## Dependency versions

`pyproject.toml` and `package.json` use version **floors / caret ranges**; the
package managers resolve the exact latest compatible release on install. Review
and pin exact versions before any real deployment.
