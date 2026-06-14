# Fake-News Detector — Implementation Plan

An automated, continuously-running pipeline that polls curated RSS feeds (mixed
reputation), detects new articles, fetches full text, scores each for
**credibility** with explanations using a **local LLM**, stores results, and
surfaces them in a dashboard.

## Detection model

A hybrid **credibility score (0–100) with bands + per-signal breakdown** — never
an opaque binary "FAKE" verdict. The MVP fuses two signals via a config-driven
**soft weighted blend** (~60% content / 40% reputation); components are stored
separately so weights can be re-tuned without re-running the LLM.

1. **Source reputation** — curated tier lookup (`trusted` / `questionable` / `unknown`).
2. **Content red-flags** — a local LLM analyzes the article text and returns
   structured JSON (sub-score + red-flag list + rationale).
3. **Cross-source corroboration** *(Phase 2)* — reserved as a weight-0
   placeholder; slots in later without schema changes.

## Engine (local, no API cost)

- **Runtime:** [Ollama](https://ollama.com) — local OpenAI-compatible HTTP service
  with native JSON-schema structured output (constrains generation to valid JSON
  via a GBNF grammar).
- **Model:** `qwen3:14b` — ~9.3 GB (Q4_K_M), 40,960-token context, tools +
  system prompts. Runs fully on a 16 GB GPU (RTX 4080 SUPER). Thinking is on by
  default — disable it / strip the think block for fast, clean structured scoring.
  Exact quant pinned at install.

## Architecture (~4 Docker Compose services)

- **worker** — APScheduler polls feeds on an interval; an asyncio pool
  (concurrency-capped) does extract → score → write.
- **discovery** — RSS/Atom + `trafilatura` full-text extraction; config-driven
  feed list spanning the reputation spectrum (so there is real signal range).
- **api** — FastAPI read endpoints (`/articles`, `/articles/{id}`).
- **db** — Postgres (raw score + components + red-flags + explanation per
  article; URL/content-hash dedup so nothing is re-scored).
- **frontend** — React + Tailwind dashboard: live color-coded feed, filter by
  source/score/time, click-through to the signal breakdown. Doubles as the
  eval-inspection view.

## Data model (Postgres, via Alembic)

- **`sources`** — `id, name, feed_url (unique), homepage, reputation_tier, active`.
- **`articles`** — `id, source_id FK, url (unique), url_canonical, content_hash,
  title, published_at, fetched_at, full_text, extraction_status`. Dedup on
  `url_canonical` + `content_hash`.
- **`scores`** — `id, article_id FK, final_score, band, reputation_subscore,
  content_subscore, corroboration_subscore (nullable), red_flags (JSONB),
  rationale, model_name, weights (JSONB), scored_at`. Re-scores append a new row;
  latest wins.

## Scoring contract (the heart of it)

`scoring/content.py` calls Ollama with `response_format` set to this JSON schema:

```jsonc
{
  "content_subscore": 0-100,            // higher = more credible content
  "red_flags": [                        // [] if none
    { "type": "clickbait|sensationalism|unsourced_claim|emotional_manipulation|missing_attribution|...",
      "severity": "low|medium|high",
      "evidence": "short quote/paraphrase" }
  ],
  "rationale": "one paragraph"
}
```

`scoring/fuse.py`: `final = round(w_content*content_subscore + w_reputation*reputation_subscore)`
(corroboration weight = 0 in MVP), then map to bands: `>=70 Likely credible`,
`40–69 Questionable`, `<40 Likely misleading`. Weights + thresholds live in
`config/scoring.yaml`.

## Milestones

- **M0 — Scaffold & infra (runnable skeleton).** `uv` project, FastAPI `/health`
  + stub `/api/articles`, Postgres + Alembic init, `docker-compose.yml`
  (`db` + `api` + `frontend`), Vite/React/Tailwind shell hitting the API.
  *Verify:* `docker compose up`, dashboard loads, `/health` green.
- **M1 — Ingestion.** `feeds.yaml` (~10–20 mixed-reputation feeds); `feedparser`
  poll → dedup → `trafilatura` extract → persist; APScheduler worker.
  *Verify:* run worker, `articles` fills with clean text; dedup holds on re-poll.
- **M2 — Scoring engine.** Ollama + `qwen3:14b`; `reputation.py`, `prompt.py` +
  schema, `content.py` (timeout/retry/concurrency cap), `fuse.py`. Worker scores
  new articles. *Verify:* scores + rationales land; malformed JSON can't crash a worker.
- **M3 — Dashboard.** FastAPI read endpoints with filters + pagination;
  `Feed.tsx` live color-coded table; `ScoreCard.tsx` signal breakdown.
  *Verify:* browse scored feed, click into a breakdown.
- **M4 — Evaluation.** `golden_set.yaml` (~30–50 labeled articles) + `run_eval.py`
  offline regression harness reporting per-item pass/fail + confusion summary.
  *Verify:* eval green; break the prompt → eval catches it.

## Phase 2 (post-MVP)

**Corroboration — implemented.** `scoring/corroboration.py`: a lexical candidate
filter (significant-token Jaccard over title+lead, within a ±72h window, other
sources only) feeds an LLM "do these report the same event?" adjudicator; the
number of distinct corroborating sources (with a trusted-source bonus) becomes a
corroboration subscore. It is **positive-only** — no corroboration → `None` →
excluded from the blend, so an uncorroborated exclusive is never penalized.
Weights are tuned (`content 0.51 / reputation 0.34 / corroboration 0.15`) so that
the uncorroborated blend renormalizes to exactly the MVP's 0.6/0.4 — no
regression (golden-set eval unchanged at 88%). Evidence (matched articles) is
stored in `scores.corroboration` (JSONB) and shown in the dashboard breakdown.

Future: candidate recall via embeddings (catches paraphrased headlines the
lexical filter misses), retroactive re-scoring when later coverage corroborates
an older article, optional alerting, Haiku/cloud A/B behind the model flag.

## Cross-cutting

- **Config-driven everything** — feeds, tiers, weights, thresholds, model name in
  YAML; no redeploy to re-tune.
- **Resilience** — per-article failures are isolated; one bad extract/LLM call
  drops that article to an error status and never kills the poll loop.
- **Tests** — unit for `fuse`/`reputation`/extraction parsing; the golden-set eval
  is the integration-level guard.
- **Dependency rule** — exact versions (Ollama, qwen3 quant, trafilatura,
  feedparser, FastAPI, SQLAlchemy) confirmed at install, not pinned from memory.

## Stack

Python 3.12 + `uv`, FastAPI, SQLAlchemy 2.0 + Alembic, `feedparser` +
`trafilatura`, `openai` client pointed at Ollama; Vite + React + TypeScript +
Tailwind; pytest + Vitest.
