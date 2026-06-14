"""initial schema: sources, articles, scores

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("feed_url", sa.String(length=1024), nullable=False),
        sa.Column("homepage", sa.String(length=1024), nullable=True),
        sa.Column("reputation_tier", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("feed_url"),
    )

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("url_canonical", sa.String(length=2048), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("extraction_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_articles_url_canonical", "articles", ["url_canonical"])
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])

    op.create_table(
        "scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("final_score", sa.Integer(), nullable=False),
        sa.Column("band", sa.String(length=32), nullable=False),
        sa.Column("reputation_subscore", sa.Integer(), nullable=False),
        sa.Column("content_subscore", sa.Integer(), nullable=False),
        sa.Column("corroboration_subscore", sa.Integer(), nullable=True),
        sa.Column("red_flags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("weights", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scores_article_id", "scores", ["article_id"])


def downgrade() -> None:
    op.drop_table("scores")
    op.drop_index("ix_articles_content_hash", table_name="articles")
    op.drop_index("ix_articles_url_canonical", table_name="articles")
    op.drop_table("articles")
    op.drop_table("sources")
