"""Read API for sources and summary stats (filter options + dashboard header)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Article, Score, Source
from app.schemas import SourceOut, StatsOut, TopicOut

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
