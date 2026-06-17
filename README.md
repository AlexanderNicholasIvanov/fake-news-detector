# Fake-News Detector

Automated pipeline that polls curated RSS feeds, fetches full article text,
scores each article for **credibility** with a **local LLM** (Ollama + `qwen3:14b`),
stores results in Postgres, and surfaces them in a React dashboard.

See [`PLAN.md`](./PLAN.md) for the full design and milestone breakdown.

**Status: MVP complete (M0–M4) + Phase 2 corroboration.** Ingestion → local-LLM
scoring → dashboard runs end-to-end, with an offline evaluation harness.

- **M0** scaffold (Postgres + Alembic, FastAPI, Vite/React/Tailwind)
- **M1** RSS ingestion (discovery, dedup, `trafilatura` full-text, APScheduler worker)
- **M2** credibility scoring (Ollama + `qwen3:14b`, structured output, soft blend);
  the content pass also classifies each article into a fixed **topic** taxonomy
- **M3** dashboard (filter by band/source/**topic**, stats, pagination, signal
  breakdown + topic column/detail view)
- **M4** evaluation (golden set + regression harness)
- **Phase 2** cross-source corroboration — an event independently reported by
  other outlets (especially trusted ones) lifts the score; a hybrid candidate
  filter (lexical token-overlap **∪** pgvector cosine nearest-neighbours over
  `nomic-embed-text` embeddings, so paraphrased coverage isn't missed) feeds an
  LLM "same event?" adjudicator. Positive-only: an uncorroborated exclusive is
  never penalized, so uncorroborated articles score exactly as in M2.

## Prerequisites

The stack runs **natively — no Docker, no admin.** You need only:

- **Python 3.12** and **Node.js 22+** on `PATH`.
- [Ollama](https://ollama.com) on the host with the scoring + embedding models:
  `ollama pull qwen3:14b` (credibility scoring) and
  `ollama pull nomic-embed-text` (corroboration recall — see Phase 2 below).
  Ollama's default bind (`127.0.0.1:11434`) is fine — everything is local now.

**PostgreSQL 16 + pgvector** are fetched automatically by the setup script as a
portable, **EDB-free** conda-forge build (under `%LOCALAPPDATA%\FakeNewsDetector`)
— nothing to install by hand, nothing to compile, no service. The launcher starts
and stops this bundled PostgreSQL with the app; its data dir persists between runs.

## Quick start (desktop app)

After the [one-time setup](#one-time-setup-native), double-click
**`run-fakenews.exe`** in the repo root. It opens as a **native desktop window**
(no browser, no address bar): a loading screen runs the preflight checks (app
setup present, Ollama + model), starts the bundled PostgreSQL, applies database
migrations, starts the API + worker + Vite dev server as **native processes**,
waits for the API to be healthy, then loads the dashboard inside the window.

**One executable is the whole lifecycle: run it to launch, close the window to
stop.** Closing the window shuts the stack down — the API, worker, and frontend
processes, plus the bundled PostgreSQL (only if the app started it; the data dir
persists, so your corpus survives a restart). The host's Ollama is left alone.

The window uses the Edge **WebView2** runtime (pre-installed on Windows 10/11)
via [pywebview]. Built from [`launcher/run_fakenews.py`](./launcher/run_fakenews.py)
with PyInstaller; rebuild with:

```bash
python launcher/build.py   # writes run-fakenews.exe to the repo root
```

[pywebview]: https://pywebview.flowrl.com/

<a id="one-time-setup-native"></a>
## One-time setup (native)

Run in a regular PowerShell (no admin):

```powershell
scripts\setup-native.ps1               # fresh, empty database
# or, to restore an existing corpus dump (backups\fakenews.dump):
scripts\setup-native.ps1 -RestoreDump
```

This downloads `micromamba`, creates a portable **PostgreSQL 16 + pgvector** env
under `%LOCALAPPDATA%\FakeNewsDetector`, initializes a data dir, builds the
backend venv + frontend deps, and creates the app role/database + schema (or
restores the dump). Then launch with `run-fakenews.exe`.

## Running by hand

The bundled PostgreSQL must be running first (the launcher does this for you):

```powershell
$pg = "$env:LOCALAPPDATA\FakeNewsDetector"
& "$pg\pg\Library\bin\pg_ctl.exe" -D "$pg\pgdata" -o "-p 5432" -w start

cp .env.example .env        # localhost defaults

# API + migrations
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# worker (separate shell)
cd backend
.\.venv\Scripts\python.exe -m app.worker

# frontend (separate shell)
cd frontend
npm run dev

# stop PostgreSQL when done
& "$pg\pg\Library\bin\pg_ctl.exe" -D "$pg\pgdata" -m fast stop
```

- Dashboard → http://localhost:5173 (fills as the worker ingests + scores)
- API health → http://localhost:8000/health → `{"status":"ok"}`
- API docs → http://localhost:8000/docs

The worker polls feeds on an interval (`POLL_INTERVAL_MINUTES`), extracts full
text, and scores up to `SCORE_BATCH_SIZE` articles per cycle.

## Evaluation (M4)

Run the golden-set regression harness through the real scoring pipeline:

```powershell
cd backend
.\.venv\Scripts\python.exe -m tests.eval.run_eval
```

It prints a per-case table + confusion matrix and exits non-zero if band
accuracy drops below the threshold — run it after changing the prompt, weights
(`backend/config/scoring.yaml`), or model.

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

## Layout

```
backend/   FastAPI app, SQLAlchemy models, Alembic migrations, config/, tests/
frontend/  Vite + React + TypeScript + Tailwind dashboard
launcher/  PyInstaller source for run-fakenews.exe (launch + close = one exe)
scripts/   setup-native.ps1 (one-time native setup: portable PostgreSQL + pgvector)
backups/   local corpus snapshots (gitignored); restorable via setup-native.ps1 -RestoreDump
PLAN.md    Full implementation plan and milestones
```

## Dependency versions

`pyproject.toml` and `package.json` use version **floors / caret ranges**; the
package managers resolve the exact latest compatible release on install. Review
and pin exact versions before any real deployment.
