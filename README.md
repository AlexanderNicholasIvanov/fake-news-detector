# Fake-News Detector

Automated pipeline that polls curated RSS feeds, fetches full article text,
scores each article for **credibility** with a **local LLM** (Ollama + `qwen3:14b`),
stores results in Postgres, and surfaces them in a React dashboard.

See [`PLAN.md`](./PLAN.md) for the full design and milestone breakdown.

**Status: MVP complete (M0–M4) + Phase 2 corroboration.** Ingestion → local-LLM
scoring → dashboard runs end-to-end, with an offline evaluation harness.

- **M0** scaffold (Postgres + Alembic, FastAPI, Vite/React/Tailwind, Docker)
- **M1** RSS ingestion (discovery, dedup, `trafilatura` full-text, APScheduler worker)
- **M2** credibility scoring (Ollama + `qwen3:14b`, structured output, soft blend);
  the content pass also classifies each article into a fixed **topic** taxonomy
- **M3** dashboard (filter by band/source/**topic**, stats, pagination, signal
  breakdown + topic column/detail view)
- **M4** evaluation (golden set + regression harness)
- **Phase 2** cross-source corroboration — an event independently reported by
  other outlets (especially trusted ones) lifts the score; a lexical candidate
  filter feeds an LLM "same event?" adjudicator. Positive-only: an uncorroborated
  exclusive is never penalized, so uncorroborated articles score exactly as in M2.

## Prerequisites

- Docker + Docker Compose
- [Ollama](https://ollama.com) on the host with `ollama pull qwen3:14b` (for scoring)
  - The Ollama **server** must listen on all interfaces so the container can reach
    it: set `OLLAMA_HOST=0.0.0.0:11434` on the host and restart Ollama.
- (For running outside Docker) Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22+

## Quick start (desktop app)

Double-click **`run-fakenews.exe`** in the repo root. It opens as a **native
desktop window** (no browser, no address bar): a loading screen runs the
preflight checks (Docker engine, Ollama + model), creates `.env` if missing,
brings the stack up, waits for the API to be healthy, then loads the dashboard
inside the window. Use **`stop-fakenews.exe`** to shut the stack down.

The window uses the Edge **WebView2** runtime (pre-installed on Windows 10/11)
via [pywebview]; the Docker stack still runs underneath and serves locally, but
the browser and `localhost` are hidden behind the app window. **Closing the
window shuts the whole stack down** (`docker compose kill` + `down`) — the
containers stop within a couple of seconds and removal finishes in the
background. The named Postgres volume is kept, so your data survives a restart.
`stop-fakenews.exe` does the same teardown from the command line.

Both binaries are built from one source ([`launcher/run_fakenews.py`](./launcher/run_fakenews.py))
with PyInstaller; behaviour is chosen by the executable's name. Rebuild with:

```bash
python launcher/build.py   # writes run-fakenews.exe + stop-fakenews.exe to repo root
```

[pywebview]: https://pywebview.flowrl.com/

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard → http://localhost:5173 (fills as the worker ingests + scores)
- API health → http://localhost:8000/health → `{"status":"ok"}`
- API docs → http://localhost:8000/docs

The `worker` service polls feeds on an interval (`POLL_INTERVAL_MINUTES`),
extracts full text, and scores up to `SCORE_BATCH_SIZE` articles per cycle.

## Evaluation (M4)

Run the golden-set regression harness through the real scoring pipeline:

```bash
docker compose run --rm -v "$PWD/backend/tests:/app/tests" worker \
  python -m tests.eval.run_eval
```

It prints a per-case table + confusion matrix and exits non-zero if band
accuracy drops below the threshold — run it after changing the prompt, weights
(`backend/config/scoring.yaml`), or model.

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
