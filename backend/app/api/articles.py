"""Read API for articles. M0 returns whatever is in the DB (empty until M1);
filters + pagination are fleshed out in M3."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Article
from app.schemas import ArticleOut, ScoreOut

router = APIRouter(prefix="/api/articles", tags=["articles"])


def _to_out(article: Article) -> ArticleOut:
    latest = article.scores[0] if article.scores else None
    return ArticleOut(
        id=article.id,
        url=article.url,
        title=article.title,
        source_name=article.source.name if article.source else None,
        published_at=article.published_at,
        extraction_status=article.extraction_status,
        latest_score=ScoreOut.model_validate(latest) if latest else None,
    )


@router.get("", response_model=list[ArticleOut])
def list_articles(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[ArticleOut]:
    stmt = select(Article).order_by(Article.created_at.desc()).limit(limit).offset(offset)
    return [_to_out(a) for a in session.scalars(stmt)]


@router.get("/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, session: Session = Depends(get_session)) -> ArticleOut:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return _to_out(article)
