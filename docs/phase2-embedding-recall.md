# Phase 2 — Embedding-based corroboration recall

**Status: planned.** Implementation plan + locked decisions. Builds on the
shipped lexical corroboration (`scoring/corroboration.py`).

## Problem

`find_candidates` is a **recall** bottleneck. It scores every other-source
article in the ±72h window by `jaccard()` of significant tokens over title+lead,
so it only fires when articles share surface words. Paraphrased coverage of the
same event slips through:

> "US, Iran reach landmark deal" ↔ "Washington and Tehran agree to terms"
> → low token overlap → never a candidate → never adjudicated → corroboration missed.

The LLM adjudicator (`_adjudicate`) already guards **precision**, so widening the
candidate net is low-risk: the unchanged "same event?" gate still decides what
counts. This is purely a recall play.

## Locked decisions

1. **DB image** — `pgvector/pgvector:pg16` (official; same PG16, so the `pgdata`
   volume is reused, no data loss). pgvector 0.8.2.
2. **Embedding model** — `nomic-embed-text` (768-dim, ~274 MB, fast; strong MTEB
   for English news). Runs on the same host Ollama as `qwen3:14b`.
3. **Filter strategy** — **hybrid union**: candidates = lexical ∪ vector-KNN,
   deduped, capped at `max_candidates`, then the existing adjudicator runs. Union
   (not replace) means recall is strictly ≥ today's; nothing lexical caught is lost.

## Design

- **Embed** the same `title + lead(full_text)` the lexical filter uses, via one
  Ollama `/api/embed` call per article (~ms; cheap next to the qwen3 content call).
- **Store** in a dedicated `article_embeddings` table (not a column on `articles`)
  so embeddings are nullable / backfilled independently — same shape as how
  `scores` hangs off `articles`. Columns: `article_id` (PK/FK), `model`, `dim`,
  `embedding vector(768)`, `created_at`. HNSW cosine index.
- **Search**: vector candidates = top-k nearest by cosine `embedding <=> :target`,
  restricted to the same `±72h / other-source / extraction_status='ok'` window,
  above a `min_similarity` floor. Union with lexical, dedup by article id, cap.
- **Lifecycle**: new articles embed at score time (in `runner.py`). A resumable
  `backfill_embeddings.py` (mirrors `backfill_topics.py`) embeds all history so
  existing articles are matchable as candidates.

## Ordered implementation steps

1. **Infra** — `docker-compose.yml`: db image → `pgvector/pgvector:pg16`.
   `pyproject.toml`: add `pgvector`.
2. **Migration `0004_embeddings`** — `CREATE EXTENSION IF NOT EXISTS vector`;
   create `article_embeddings`; add HNSW cosine index on `embedding`.
3. **Model** — `app/models.py`: `ArticleEmbedding` using `pgvector.sqlalchemy.Vector`.
4. **Embeddings module** — `app/scoring/embeddings.py`: `async embed(client, text)
   -> list[float] | None` (Ollama `/api/embed`, failure-tolerant); `store_embedding`
   upsert helper; `EMBED_MODEL`/`EMBED_DIM` from config.
5. **Hybrid filter** — `corroboration.py`: add `_vector_candidates(session, article,
   target_vec)`; `find_candidates` computes the target embedding, unions lexical +
   vector, dedups by id, caps at `max_candidates`. Lexical path stays intact as a
   fallback when embeddings are absent.
6. **Wire into runner** — `runner.py`: after a successful score, embed + store the
   article so it is available as a future candidate.
7. **Backfill** — `app/scoring/backfill_embeddings.py`: resumable, embeds every
   `extraction_status='ok'` article missing an embedding; progress every 25.
8. **Config** — `config/scoring.yaml` `corroboration:` block:
   `embedding_model: nomic-embed-text`, `embedding_dim: 768`,
   `embedding_candidates: 8`, `min_similarity: 0.x` (tune on live data).
9. **Validation** — see below.
10. **Docs** — update `PLAN.md` Phase 2 + `README.md` (prereq: `ollama pull
    nomic-embed-text`).

## Validation plan

- **Recall metric** — on a set of known multi-source events, confirm vector
  surfaces sibling articles the lexical filter missed (the point of the feature).
- **Precision guard** — re-run a live event (e.g. the US-Iran deal): the
  adjudicator must still reject related-but-different stories. No false-positive
  corroboration.
- **No regression** — golden-set eval stays ≥ threshold (expected unchanged:
  corroboration is positive-only and the golden set is isolated single articles).

## Notes / risks

- **Lock-in**: `vector(768)` is tied to nomic. Storing `model`+`dim` makes a model
  swap a re-embed/backfill, not a schema break.
- **Ordering**: candidates need embeddings first — run the backfill before relying
  on vector recall.
- **Validation is Docker-gated** — needs the stack + `nomic-embed-text` pulled.
