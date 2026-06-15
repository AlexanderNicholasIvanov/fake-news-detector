"""Retroactive corroboration re-scoring.

When later coverage corroborates an older article — or when the candidate filter
itself improves (e.g. embedding recall) — an already-scored article's
corroboration is stale. This recomputes ONLY the corroboration signal (content,
reputation, topic, red-flags and rationale are stable and carried forward),
re-fuses, and appends a new Score row (latest wins) — but only when the result
actually changes, so re-runs are idempotent and don't churn the table.

Cheap by design: no content LLM call, and the stored embedding is reused rather
than recomputed. At most one adjudication call (only when candidates exist).
"""

from __future__ import annotations

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Article, ArticleEmbedding, Score
from app.scoring.corroboration import score_corroboration
from app.scoring.fuse import fuse
from app.scoring.settings import WEIGHTS


def _latest_score(session: Session, article_id: int) -> Score | None:
    return session.scalars(
        select(Score)
        .where(Score.article_id == article_id)
        .order_by(Score.id.desc())
        .limit(1)
    ).first()


def _matched_ids(evidence: dict | None) -> set[int]:
    return {m["article_id"] for m in (evidence or {}).get("matched", [])}


async def rescore_corroboration(
    session: Session, client: httpx.AsyncClient, article_id: int
) -> str:
    """Recompute corroboration for one already-scored article and append an
    updated Score if it changed. Returns "updated" | "unchanged" | "skipped"."""
    latest = _latest_score(session, article_id)
    if latest is None:
        return "skipped"  # never scored — nothing to carry forward

    row = session.execute(
        select(
            Article.title,
            Article.full_text,
            Article.source_id,
            func.coalesce(Article.published_at, Article.created_at),
        ).where(Article.id == article_id)
    ).first()
    if row is None:
        return "skipped"
    title, text, source_id, when = row

    emb = session.get(ArticleEmbedding, article_id)
    target_vec = list(emb.embedding) if emb is not None else None

    article = {
        "id": article_id, "title": title, "full_text": text,
        "source_id": source_id, "when": when,
    }
    corro_subscore, corro_evidence = await score_corroboration(
        session, client, article, target_vec
    )

    new_final, new_band = fuse(
        latest.content_subscore, latest.reputation_subscore, corro_subscore
    )
    unchanged = (
        corro_subscore == latest.corroboration_subscore
        and new_final == latest.final_score
        and _matched_ids(corro_evidence) == _matched_ids(latest.corroboration)
    )
    if unchanged:
        return "unchanged"

    session.add(
        Score(
            article_id=article_id,
            final_score=new_final,
            band=new_band,
            topic=latest.topic,
            reputation_subscore=latest.reputation_subscore,
            content_subscore=latest.content_subscore,
            corroboration_subscore=corro_subscore,
            corroboration=corro_evidence,
            red_flags=latest.red_flags,
            rationale=latest.rationale,
            model_name=latest.model_name,
            weights=WEIGHTS,
        )
    )
    session.commit()
    return "updated"


async def rescore_corroborators(
    client: httpx.AsyncClient, evidence: dict | None
) -> int:
    """Reactively re-score the older articles a just-scored article corroborates.

    Corroboration is symmetric within the window: if B corroborates A, then A is
    now corroborated by B but was scored before B existed. Re-score each such A so
    its stored score reflects the new coverage. Non-recursive (a re-score does not
    trigger further re-scores) and failure-isolated. Returns the count updated.
    """
    updated = 0
    for aid in _matched_ids(evidence):
        try:
            with SessionLocal() as session:
                if await rescore_corroboration(session, client, aid) == "updated":
                    updated += 1
        except Exception as exc:
            print(f"[rescore] error article={aid}: {exc}", flush=True)
    return updated
