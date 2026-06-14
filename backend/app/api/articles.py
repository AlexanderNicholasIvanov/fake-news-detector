"""Read API for articles: filtering, sorting, pagination, and detail."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Article, Score
from app.schemas import ArticleDetailOut, ArticleOut, ScoreOut

router = APIRouter(prefix="/api/articles", tags=["articles"])


def _latest_score_subq():
    """article_id -> id of its most recent score (max id == latest insert)."""
    return (
        select(Score.article_id.label("aid"), func.max(Score.id).label("sid"))
        .group_by(Score.article_id)
        .subquery()
    )


def _to_out(article: Article, score: Score | None, *, detail: bool = False) -> ArticleOut:
    common = dict(
        id=article.id,
        url=article.url,
        title=article.title,
        source_name=article.source.name if article.source else None,
        source_tier=article.source.reputation_tier if article.source else None,
        published_at=article.published_at,
        extraction_status=article.extraction_status,
        latest_score=ScoreOut.model_validate(score) if score else None,
    )
    if detail:
        return ArticleDetailOut(full_text=article.full_text, **common)
    return ArticleOut(**common)


@router.get("", response_model=list[ArticleOut])
def list_articles(
    band: str | None = Query(None, description="credible | questionable | misleading"),
    topic: str | None = Query(None, description="filter by classified topic"),
    source_id: int | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    status: str | None = Query("ok", description="extraction_status filter; null for any"),
    order: Literal["recent", "score_desc", "score_asc"] = "recent",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[ArticleOut]:
    latest = _latest_score_subq()
    stmt = (
        select(Article, Score)
        .join(latest, latest.c.aid == Article.id, isouter=True)
        .join(Score, Score.id == latest.c.sid, isouter=True)
    )
    if status:
        stmt = stmt.where(Article.extraction_status == status)
    if source_id is not None:
        stmt = stmt.where(Article.source_id == source_id)
    if band:
        stmt = stmt.where(Score.band == band)
    if topic:
        stmt = stmt.where(Score.topic == topic)
    if min_score is not None:
        stmt = stmt.where(Score.final_score >= min_score)

    if order == "score_desc":
        stmt = stmt.order_by(Score.final_score.desc().nulls_last())
    elif order == "score_asc":
        stmt = stmt.order_by(Score.final_score.asc().nulls_last())
    else:
        stmt = stmt.order_by(Article.created_at.desc())

    stmt = stmt.limit(limit).offset(offset)
    return [_to_out(a, s) for a, s in session.execute(stmt)]


@router.get("/{article_id}", response_model=ArticleDetailOut)
def get_article(article_id: int, session: Session = Depends(get_session)) -> ArticleDetailOut:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    score = article.scores[0] if article.scores else None
    return _to_out(article, score, detail=True)
