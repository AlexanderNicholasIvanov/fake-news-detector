"""Ingestion worker: polls feeds on an interval, extracts full text, persists.

Run continuously:   python -m app.worker
Run a single cycle: python -m app.worker --once
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import settings
from app.db import SessionLocal
from app.ingest.extract import extract_many
from app.ingest.feeds import discover_new_articles, load_sources
from app.models import Article


def _wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    """Block until the `sources` table is queryable (api applies migrations)."""
    for attempt in range(1, retries + 1):
        try:
            with SessionLocal() as session:
                session.scalar(select(Article.id).limit(1))
            return
        except (OperationalError, ProgrammingError) as exc:
            print(f"[worker] waiting for db ({attempt}/{retries}): {exc}", flush=True)
            import time

            time.sleep(delay)
    raise RuntimeError("database/schema not ready after retries")


async def _extract_pending() -> int:
    """Fetch + extract all pending articles. Returns the count marked ok."""
    with SessionLocal() as session:
        pending = list(
            session.scalars(
                select(Article).where(Article.extraction_status == "pending")
            )
        )
        items = [(a.id, a.url) for a in pending]

    if not items:
        return 0

    results = await extract_many(items)

    ok = 0
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        # Content hashes already present (in other articles) → mark as duplicate.
        for r in results:
            article = session.get(Article, r["id"])
            if article is None:
                continue
            article.fetched_at = now
            if r["status"] != "ok":
                article.extraction_status = "failed"
                continue
            dupe = session.scalar(
                select(Article.id)
                .where(Article.content_hash == r["content_hash"], Article.id != r["id"])
                .limit(1)
            )
            article.full_text = r["full_text"]
            article.content_hash = r["content_hash"]
            article.extraction_status = "duplicate" if dupe else "ok"
            if not dupe:
                ok += 1
        session.commit()
    return ok


async def run_cycle() -> None:
    """One full poll → discover → extract pass. Failures are isolated."""
    try:
        with SessionLocal() as session:
            new = await asyncio.to_thread(discover_new_articles, session)
        extracted = await _extract_pending()
        print(f"[worker] cycle done: {new} new, {extracted} extracted", flush=True)
    except Exception as exc:  # never let a bad cycle kill the loop
        print(f"[worker] cycle error: {exc}", flush=True)


async def main() -> None:
    run_once = "--once" in sys.argv
    _wait_for_db()

    with SessionLocal() as session:
        n = await asyncio.to_thread(load_sources, session)
    print(f"[worker] loaded {n} active sources", flush=True)

    await run_cycle()
    if run_once:
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_cycle, "interval", minutes=settings.poll_interval_minutes, id="poll"
    )
    scheduler.start()
    print(
        f"[worker] scheduled every {settings.poll_interval_minutes} min; running.",
        flush=True,
    )
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
