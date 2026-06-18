"""Read API for sources and summary stats (filter options + dashboard header)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Article, Score, Source
from app.schemas import ScoringStatusOut, SourceOut, StatsOut, TopicOut
from app.scoring.embeddings import EMBED_MODEL

router = APIRouter(prefix="/api", tags=["meta"])


def _latest_score_ids():
    """Subquery of the latest score id per article (max id == latest insert)."""
    return select(func.max(Score.id).label("sid")).group_by(Score.article_id).subquery()


@router.get("/sources", response_model=list[SourceOut])
def list_sources(session: Session = Depends(get_session)) -> list[SourceOut]:
    stmt = (
        select(Source.id, Source.name, Source.reputation_tier, func.count(Article.id))
        .join(Article, Article.source_id == Source.id, isouter=True)
        .group_by(Source.id)
        .order_by(Source.name)
    )
    return [
        SourceOut(id=sid, name=name, reputation_tier=tier, article_count=count)
        for sid, name, tier, count in session.execute(stmt)
    ]


@router.get("/stats", response_model=StatsOut)
def stats(session: Session = Depends(get_session)) -> StatsOut:
    total = session.scalar(select(func.count()).select_from(Article)) or 0
    extracted = session.scalar(
        select(func.count()).select_from(Article).where(Article.extraction_status == "ok")
    ) or 0
    # latest score per article, then count by band
    latest = _latest_score_ids()
    band_rows = session.execute(
        select(Score.band, func.count())
        .where(Score.id.in_(select(latest.c.sid)))
        .group_by(Score.band)
    ).all()
    bands = {band: count for band, count in band_rows}
    scored = sum(bands.values())
    return StatsOut(total_articles=total, extracted=extracted, scored=scored, bands=bands)


@router.get("/scoring-status", response_model=ScoringStatusOut)
def scoring_status() -> ScoringStatusOut:
    """Is the scoring engine (Ollama) reachable, and are the required models pulled?

    Drives the dashboard's engine indicator. A best-effort probe of the same Ollama
    the worker scores against — never raises; an unreachable engine reports offline.
    """
    scoring_model = settings.scoring_model
    out = ScoringStatusOut(
        engine="offline",
        scoring_model=scoring_model,
        scoring_model_ready=False,
        embedding_model=EMBED_MODEL,
        embedding_model_ready=False,
    )
    try:
        resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
        resp.raise_for_status()
        names = {m.get("name", "") for m in resp.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return out  # offline

    def _present(model: str) -> bool:
        base = model.split(":")[0]
        return model in names or any(n.split(":")[0] == base for n in names)

    out.engine = "online"
    out.scoring_model_ready = _present(scoring_model)
    out.embedding_model_ready = _present(EMBED_MODEL)
    return out


@router.get("/topics", response_model=list[TopicOut])
def list_topics(session: Session = Depends(get_session)) -> list[TopicOut]:
    """Topics present among the latest scores, with counts (for the filter)."""
    latest = _latest_score_ids()
    rows = session.execute(
        select(Score.topic, func.count())
        .where(Score.id.in_(select(latest.c.sid)), Score.topic.is_not(None))
        .group_by(Score.topic)
        .order_by(func.count().desc())
    ).all()
    return [TopicOut(topic=topic, count=count) for topic, count in rows]
