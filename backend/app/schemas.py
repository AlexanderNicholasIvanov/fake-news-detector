"""Pydantic API response schemas. (LLM I/O contracts arrive in M2.)"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    final_score: int
    band: str
    reputation_subscore: int
    content_subscore: int
    corroboration_subscore: int | None = None
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
    published_at: datetime | None = None
    extraction_status: str
    latest_score: ScoreOut | None = None
