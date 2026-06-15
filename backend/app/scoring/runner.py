"""Score `ok` articles that don't yet have a credibility score."""

from __future__ import annotations

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Article, Score, Source
from app.scoring.content import score_content
from app.scoring.corroboration import score_corroboration
from app.scoring.embeddings import embed, embed_text, store_embedding
from app.scoring.fuse import fuse
from app.scoring.reputation import reputation_subscore
from app.scoring.settings import MODEL, WEIGHTS


def _unscored(session: Session, limit: int) -> list[tuple]:
    """ok+unscored articles, with the fields content + corroboration scoring need."""
    stmt = (
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
        .order_by(Article.created_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).all())


async def score_pending(limit: int) -> int:
    """Score up to `limit` unscored articles. Per-article LLM failures are
    isolated. Returns the number scored. Runs sequentially — Ollama serializes a
    single model anyway."""
    with SessionLocal() as session:
        rows = _unscored(session, limit)
    if not rows:
        return 0

    scored = 0
    async with httpx.AsyncClient() as client:
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

            # Phase 2: embed the article once — reused for corroboration matching
            # and stored so future articles can match against it. Failure-tolerant.
            target_vec = None
            try:
                target_vec = await embed(client, embed_text(title, text))
            except Exception as exc:
                print(f"[score] embed error id={article_id}: {exc}", flush=True)

            # Phase 2: cross-source corroboration (positive-only; None if no match).
            # Candidates = lexical token-overlap UNION cosine nearest-neighbours.
            corro_subscore, corro_evidence = None, None
            try:
                article = {
                    "id": article_id, "title": title, "full_text": text,
                    "source_id": source_id, "when": when,
                }
                with SessionLocal() as session:
                    corro_subscore, corro_evidence = await score_corroboration(
                        session, client, article, target_vec
                    )
            except Exception as exc:
                print(f"[score] corroboration error id={article_id}: {exc}", flush=True)

            if target_vec:
                try:
                    with SessionLocal() as session:
                        store_embedding(session, article_id, target_vec)
                except Exception as exc:
                    print(f"[score] embed store error id={article_id}: {exc}", flush=True)

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
    return scored
