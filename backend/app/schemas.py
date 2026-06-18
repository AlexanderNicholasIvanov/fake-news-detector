"""Pydantic API response schemas. (LLM I/O contracts arrive in M2.)"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    final_score: int
    band: str
    topic: str | None = None
    reputation_subscore: int
    content_subscore: int
    corroboration_subscore: int | None = None
    corroboration: dict | None = None
    red_flags: list = []
    rationale: str | None = None
    model_name: str
    scored_at: datetime


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str | None = None
    source_name: str | None = None
    source_tier: str | None = None
    published_at: datetime | None = None
    extraction_status: str
    latest_score: ScoreOut | None = None


class ArticleDetailOut(ArticleOut):
    full_text: str | None = None


class SourceOut(BaseModel):
    id: int
    name: str
    reputation_tier: str
    article_count: int = 0


class StatsOut(BaseModel):
    total_articles: int
    extracted: int
    scored: int
    bands: dict[str, int]


class TopicOut(BaseModel):
    topic: str
    count: int


class ScoringStatusOut(BaseModel):
    """Health of the scoring engine (Ollama) for the dashboard indicator."""

    engine: str  # "online" | "offline"
    scoring_model: str
    scoring_model_ready: bool
    embedding_model: str
    embedding_model_ready: bool
