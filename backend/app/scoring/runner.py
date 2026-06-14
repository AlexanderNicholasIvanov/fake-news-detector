"""Score `ok` articles that don't yet have a credibility score."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Article, Score, Source
from app.scoring.content import score_content
from app.scoring.fuse import fuse
from app.scoring.reputation import reputation_subscore
from app.scoring.settings import MODEL, WEIGHTS


def _unscored(session: Session, limit: int) -> list[tuple]:
    """(article_id, title, full_text, url, reputation_tier) for ok+unscored articles."""
    stmt = (
        select(
            Article.id,
            Article.title,
            Article.full_text,
            Article.url,
            Source.reputation_tier,
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
        for article_id, title, text, url, tier in rows:
            try:
                result = await score_content(client, title, text)
            except Exception as exc:
                print(f"[score] llm error id={article_id}: {exc}", flush=True)
                continue
            if result is None:
                print(f"[score] unparseable response id={article_id}", flush=True)
                continue

            rep_subscore, _ = reputation_subscore(tier, url)
            final, band = fuse(result["content_subscore"], rep_subscore)

            with SessionLocal() as session:
                session.add(
                    Score(
                        article_id=article_id,
                        final_score=final,
                        band=band,
                        reputation_subscore=rep_subscore,
                        content_subscore=result["content_subscore"],
                        corroboration_subscore=None,
                        red_flags=result["red_flags"],
                        rationale=result["rationale"],
                        model_name=MODEL,
                        weights=WEIGHTS,
                    )
                )
                session.commit()
            scored += 1
    return scored
