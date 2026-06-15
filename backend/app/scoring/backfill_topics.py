"""Backfill `topic` for already-scored articles whose latest score predates the
topic feature. Classifies each via a minimal topic-only LLM call and updates the
latest Score row IN PLACE — credibility scores and corroboration are untouched.

Resumable: only targets latest scores with topic IS NULL, so re-running continues
where an interrupted run left off.

Run:  docker compose run --rm worker python -m app.scoring.backfill_topics
"""

from __future__ import annotations

import asyncio
import json

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Article, Score
from app.scoring.prompt import TOPICS, build_user_prompt
from app.scoring.settings import MODEL

REQUEST_TIMEOUT = 120.0

_SYSTEM = (
    "You classify a news article into exactly one subject from this fixed list: "
    + ", ".join(TOPICS)
    + '. Pick the single best fit; use "other" only when none clearly applies. '
    "This is about the article's subject, not its credibility."
)
_SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string", "enum": TOPICS}},
    "required": ["topic"],
}


async def classify_topic(client: httpx.AsyncClient, title, text) -> str | None:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": build_user_prompt(title, text)},
        ],
        "stream": False,
        "think": False,
        "format": _SCHEMA,
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat", json=payload, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    try:
        topic = json.loads(content).get("topic")
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None
    return topic if topic in TOPICS else "other"


def _pending(session: Session) -> list[tuple]:
    """(score_id, title, full_text) for latest scores still missing a topic."""
    latest = (
        select(func.max(Score.id).label("sid")).group_by(Score.article_id).subquery()
    )
    return list(
        session.execute(
            select(Score.id, Article.title, Article.full_text)
            .join(Article, Article.id == Score.article_id)
            .where(Score.id.in_(select(latest.c.sid)), Score.topic.is_(None))
            .order_by(Score.id)
        ).all()
    )


async def main() -> int:
    with SessionLocal() as session:
        rows = _pending(session)
    total = len(rows)
    print(f"[backfill] {total} scores to classify", flush=True)
    if not total:
        return 0

    done = 0
    async with httpx.AsyncClient() as client:
        for score_id, title, text in rows:
            try:
                topic = await classify_topic(client, title, text)
            except Exception as exc:
                print(f"[backfill] error score={score_id}: {exc}", flush=True)
                continue
            if topic is None:
                print(f"[backfill] unparseable score={score_id}", flush=True)
                continue
            with SessionLocal() as session:
                session.execute(
                    update(Score).where(Score.id == score_id).values(topic=topic)
                )
                session.commit()
            done += 1
            if done % 25 == 0:
                print(f"[backfill] {done}/{total} classified", flush=True)

    print(f"[backfill] done: {done}/{total} classified", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
