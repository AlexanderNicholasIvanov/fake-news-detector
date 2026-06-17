"""Ingestion + grading worker.

Polls feeds on an interval and extracts full text, and separately grades articles
for credibility. Grading runs as a continuous background loop that drains the
unscored backlog oldest-first, one article at a time — each article's score is
committed as soon as it is produced, so the dashboard fills in one by one.

To keep startup responsive, grading does not begin until the API is serving: the
app (dashboard) loads first, then grading starts.

Run continuously:   python -m app.worker
Run a single pass:  python -m app.worker --once   (one ingest + one grade batch)
"""

from __future__ import annotations

import asyncio
import sys
import time
import urllib.request
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import settings
from app.db import SessionLocal
from app.ingest.extract import extract_many
from app.ingest.feeds import discover_new_articles, load_sources
from app.models import Article
from app.scoring.runner import score_pending


def _wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    """Block until the `sources` table is queryable (api applies migrations)."""
    for attempt in range(1, retries + 1):
        try:
            with SessionLocal() as session:
                session.scalar(select(Article.id).limit(1))
            return
        except (OperationalError, ProgrammingError) as exc:
            print(f"[worker] waiting for db ({attempt}/{retries}): {exc}", flush=True)
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


async def ingest_cycle() -> None:
    """Discover new articles + extract full text (no grading). Failures isolated."""
    try:
        with SessionLocal() as session:
            new = await asyncio.to_thread(discover_new_articles, session)
        extracted = await _extract_pending()
        print(f"[worker] ingest: {new} new, {extracted} extracted", flush=True)
    except Exception as exc:  # never let a bad cycle kill the loop
        print(f"[worker] ingest error: {exc}", flush=True)


async def _grade_batch() -> int:
    """Grade the next batch of unscored articles (oldest-first; each commits as it is
    graded). Returns the number graded. Per-article failures are isolated inside
    score_pending; a transport-level failure here returns 0 so the loop can retry."""
    try:
        return await score_pending(settings.score_batch_size)
    except Exception as exc:
        print(f"[worker] grade error: {exc}", flush=True)
        return 0


def _api_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


async def _wait_for_api(url: str, max_seconds: int) -> bool:
    """Wait (bounded) for the API to be serving, so the dashboard loads before grading
    starts. Returns True if it came up, False if we gave up (then grade anyway)."""
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        if await asyncio.to_thread(_api_ready, url):
            return True
        await asyncio.sleep(2)
    return False


async def grading_loop() -> None:
    """Grade unscored articles continuously, oldest-first, one by one (each commits as
    produced). When the backlog is clear, idle and re-check periodically so newly
    ingested articles get picked up."""
    while True:
        graded = await _grade_batch()
        if graded == 0:
            await asyncio.sleep(settings.grade_idle_seconds)


async def main() -> None:
    run_once = "--once" in sys.argv
    _wait_for_db()

    with SessionLocal() as session:
        n = await asyncio.to_thread(load_sources, session)
    print(f"[worker] loaded {n} active sources", flush=True)

    if run_once:
        await ingest_cycle()
        await _grade_batch()
        return

    # Ingest on a timer (independent of grading).
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        ingest_cycle, "interval", minutes=settings.poll_interval_minutes, id="ingest"
    )
    scheduler.start()

    # Load first, then grade: hold the GPU-heavy grading until the API is serving
    # (bounded wait) so the dashboard comes up promptly. Then kick an initial ingest
    # in the background and grade the unscored backlog continuously, one by one.
    up = await _wait_for_api(
        settings.api_health_url, settings.grade_start_after_api_seconds
    )
    print(
        f"[worker] app {'is up' if up else 'health wait timed out'}; "
        "grading unscored articles one by one",
        flush=True,
    )
    _initial_ingest = asyncio.create_task(ingest_cycle())  # noqa: F841 fire-and-forget
    await grading_loop()


if __name__ == "__main__":
    asyncio.run(main())
