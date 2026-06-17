"""Score `ok` articles that don't yet have a credibility score."""

from __future__ import annotations

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Article, Score, Source
from app.scoring.content import score_content
from app.scoring.corroboration import score_corroboration
from app.scoring.embeddings import embed, embed_text, store_embedding
from app.scoring.fuse import fuse
from app.scoring.reputation import reputation_subscore
from app.scoring.rescore import rescore_corroborators
from app.scoring.settings import CORROBORATION, MODEL, WEIGHTS


def _unscored(session: Session, limit: int) -> list[tuple]:
    """ok+unscored articles to grade next, with the fields content + corroboration
    scoring need.

    Hybrid ordering: most of the batch is newest-first, so freshly ingested news is
    scored promptly; a slice (score_backlog_share) is the OLDEST unscored, so any
    backlog still drains and no article is permanently starved. This balances
    "recent news is current" against "the backlog eventually clears". Strict
    newest-first would starve an old backlog; strict oldest-first delays recent news
    behind the whole backlog.
    """
    base = (
        select(
            Article.id,
            Article.title,
            Article.full_text,
            Article.url,
            Source.reputation_tier,
            Article.source_id,
            func.coalesce(Article.published_at, Article.created_at),
        )
        .join(Source, Source.id == Article.source_id)
        .outerjoin(Score, Score.article_id == Article.id)
        .where(Article.extraction_status == "ok", Score.id.is_(None))
    )
    old_n = int(limit * float(settings.score_backlog_share)) if limit > 1 else 0
    new_n = limit - old_n

    # Newest-first slice first (priority), then fill from the oldest; dedup by id so
    # a small backlog (where the two slices overlap) isn't double-counted.
    rows: dict[int, tuple] = {}
    for r in session.execute(base.order_by(Article.created_at.desc()).limit(new_n)).all():
        rows[r[0]] = r
    if old_n:
        for r in session.execute(base.order_by(Article.created_at.asc()).limit(old_n)).all():
            rows.setdefault(r[0], r)
    return list(rows.values())


async def _embed_pass(
    client: httpx.AsyncClient, rows: list[tuple]
) -> dict[int, list[float]]:
    """Embed every article and store it, in one pass — so the embedding model
    stays resident (one load, not a qwen3<->nomic swap per article). Returns the
    in-memory {article_id: vector} for reuse by corroboration. Failure-tolerant."""
    vecs: dict[int, list[float]] = {}
    for article_id, title, text, *_ in rows:
        try:
            vec = await embed(client, embed_text(title, text))
        except Exception as exc:
            print(f"[score] embed error id={article_id}: {exc}", flush=True)
            continue
        if not vec:
            continue
        vecs[article_id] = vec
        try:
            with SessionLocal() as session:
                store_embedding(session, article_id, vec)
        except Exception as exc:
            print(f"[score] embed store error id={article_id}: {exc}", flush=True)
    return vecs


async def score_pending(limit: int) -> int:
    """Score up to `limit` unscored articles. Per-article LLM failures are
    isolated. Returns the number scored.

    Two passes to avoid model-swap thrash: first embed everything (embedding model
    resident), then score + corroborate everything (qwen3 resident — corroboration
    adjudication shares that model, so the scoring pass makes no model switches)."""
    with SessionLocal() as session:
        rows = _unscored(session, limit)
    if not rows:
        return 0

    scored = 0
    async with httpx.AsyncClient() as client:
        vecs = await _embed_pass(client, rows)

        for article_id, title, text, url, tier, source_id, when in rows:
            try:
                result = await score_content(client, title, text)
            except Exception as exc:
                print(f"[score] llm error id={article_id}: {exc}", flush=True)
                continue
            if result is None:
                print(f"[score] unparseable response id={article_id}", flush=True)
                continue

            rep_subscore, _ = reputation_subscore(tier, url)

            # Phase 2: cross-source corroboration (positive-only; None if no match).
            # Candidates = lexical token-overlap UNION cosine nearest-neighbours;
            # the embedding was computed in the pass above (no re-embed here).
            corro_subscore, corro_evidence = None, None
            try:
                article = {
                    "id": article_id, "title": title, "full_text": text,
                    "source_id": source_id, "when": when,
                }
                with SessionLocal() as session:
                    corro_subscore, corro_evidence = await score_corroboration(
                        session, client, article, vecs.get(article_id)
                    )
            except Exception as exc:
                print(f"[score] corroboration error id={article_id}: {exc}", flush=True)

            final, band = fuse(result["content_subscore"], rep_subscore, corro_subscore)

            with SessionLocal() as session:
                session.add(
                    Score(
                        article_id=article_id,
                        final_score=final,
                        band=band,
                        topic=result["topic"],
                        reputation_subscore=rep_subscore,
                        content_subscore=result["content_subscore"],
                        corroboration_subscore=corro_subscore,
                        corroboration=corro_evidence,
                        red_flags=result["red_flags"],
                        rationale=result["rationale"],
                        model_name=MODEL,
                        weights=WEIGHTS,
                    )
                )
                session.commit()
            scored += 1

            # Reactive retroactive re-score: this article (now persisted) may
            # corroborate older articles that were scored before it existed —
            # refresh their stored corroboration. Failure-isolated, non-recursive.
            if CORROBORATION.get("retroactive_rescore", True) and corro_evidence:
                try:
                    n = await rescore_corroborators(client, corro_evidence)
                    if n:
                        print(f"[score] retroactively re-scored {n} article(s) "
                              f"corroborated by id={article_id}", flush=True)
                except Exception as exc:
                    print(f"[score] retroactive rescore error id={article_id}: {exc}",
                          flush=True)
    return scored
