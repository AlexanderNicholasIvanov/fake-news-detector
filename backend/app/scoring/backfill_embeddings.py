"""Backfill embeddings for articles that predate the embedding-recall feature.

Candidates for cosine matching must already have a stored embedding, so this
embeds every `extraction_status='ok'` article that is missing one. Credibility
scores are untouched — this only populates `article_embeddings`.

Resumable: only targets articles with no embedding row, so re-running continues
where an interrupted run left off.

Run:  docker compose run --rm worker python -m app.scoring.backfill_embeddings
"""

from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Article, ArticleEmbedding
from app.scoring.embeddings import embed, embed_text, store_embedding


def _pending(session: Session) -> list[tuple]:
    """(id, title, full_text) for ok articles with no embedding yet."""
    return list(
        session.execute(
            select(Article.id, Article.title, Article.full_text)
            .outerjoin(ArticleEmbedding, ArticleEmbedding.article_id == Article.id)
            .where(Article.extraction_status == "ok", ArticleEmbedding.article_id.is_(None))
            .order_by(Article.id)
        ).all()
    )


async def main() -> int:
    with SessionLocal() as session:
        rows = _pending(session)
    total = len(rows)
    print(f"[embed-backfill] {total} articles to embed", flush=True)
    if not total:
        return 0

    done = 0
    async with httpx.AsyncClient() as client:
        for article_id, title, text in rows:
            try:
                vec = await embed(client, embed_text(title, text))
            except Exception as exc:
                print(f"[embed-backfill] error id={article_id}: {exc}", flush=True)
                continue
            if vec is None:
                print(f"[embed-backfill] no embedding id={article_id}", flush=True)
                continue
            with SessionLocal() as session:
                store_embedding(session, article_id, vec)
            done += 1
            if done % 25 == 0:
                print(f"[embed-backfill] {done}/{total} embedded", flush=True)

    print(f"[embed-backfill] done: {done}/{total} embedded", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
