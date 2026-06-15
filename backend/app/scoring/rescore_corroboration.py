"""Retroactively re-score corroboration for already-scored articles.

Recomputes corroboration (now hybrid lexical+embedding recall) for the latest
score of every article and appends an updated Score where it changed — so the
historical backlog reflects the improved candidate filter, not just newly-scored
articles. Idempotent: a second run finds nothing changed and appends nothing.

Run all:       docker compose run --rm worker python -m app.scoring.rescore_corroboration
Run a subset:  docker compose run --rm worker python -m app.scoring.rescore_corroboration 1040 322
"""

from __future__ import annotations

import asyncio
import sys

import httpx
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Score
from app.scoring.rescore import rescore_corroboration


def _latest_article_ids() -> list[int]:
    """article_ids that have at least one score, ordered oldest-id first."""
    latest = (
        select(func.max(Score.id).label("sid")).group_by(Score.article_id).subquery()
    )
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(Score.article_id)
                .where(Score.id.in_(select(latest.c.sid)))
                .order_by(Score.article_id)
            ).all()
        )


async def main() -> int:
    arg_ids = [int(a) for a in sys.argv[1:]]
    ids = arg_ids or _latest_article_ids()
    total = len(ids)
    print(f"[rescore] {total} articles to re-evaluate", flush=True)
    if not total:
        return 0

    counts = {"updated": 0, "unchanged": 0, "skipped": 0}
    async with httpx.AsyncClient() as client:
        for i, aid in enumerate(ids, 1):
            try:
                with SessionLocal() as session:
                    status = await rescore_corroboration(session, client, aid)
            except Exception as exc:
                print(f"[rescore] error article={aid}: {exc}", flush=True)
                continue
            counts[status] += 1
            if i % 25 == 0:
                print(f"[rescore] {i}/{total}  {counts}", flush=True)

    print(f"[rescore] done: {counts['updated']} updated, "
          f"{counts['unchanged']} unchanged, {counts['skipped']} skipped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
