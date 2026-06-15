"""ORM models. Tier/band/status are stored as plain strings (no native PG enums)
to keep migrations simple; allowed values live alongside as module constants."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# nomic-embed-text dimensionality (kept in sync with config/scoring.yaml and the
# 0004_embeddings migration). A model swap to a different dim => re-embed + migration.
EMBED_DIM = 768

# Allowed string values (enforced in app code / validation, not the DB schema).
REPUTATION_TIERS = ("trusted", "questionable", "unknown")
EXTRACTION_STATUSES = ("pending", "ok", "failed", "duplicate")
BANDS = ("credible", "questionable", "misleading")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    feed_url: Mapped[str] = mapped_column(String(1024), unique=True)
    homepage: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    reputation_tier: Mapped[str] = mapped_column(String(32), default="unknown")
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    articles: Mapped[list["Article"]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    url_canonical: Mapped[str] = mapped_column(String(2048), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="articles")
    scores: Mapped[list["Score"]] = relationship(
        back_populates="article", order_by="Score.scored_at.desc()"
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    final_score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(32))
    topic: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    reputation_subscore: Mapped[int] = mapped_column(Integer)
    content_subscore: Mapped[int] = mapped_column(Integer)
    corroboration_subscore: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase 2: which other-source articles corroborate this event (nullable JSONB);
    # null/[] = no corroboration found, so corroboration was excluded from the blend.
    corroboration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    red_flags: Mapped[list] = mapped_column(JSONB, default=list)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(128))
    weights: Mapped[dict] = mapped_column(JSONB, default=dict)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    article: Mapped[Article] = relationship(back_populates="scores")


class ArticleEmbedding(Base):
    """One dense embedding per article (1:1), used as the vector side of the
    hybrid corroboration candidate filter. Backfilled independently of scoring."""

    __tablename__ = "article_embeddings"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String(128))
    dim: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
