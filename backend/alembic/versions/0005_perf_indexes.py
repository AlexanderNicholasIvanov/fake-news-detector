"""performance indexes: latest-score lookups, corroboration window scan, worker filters

Revision ID: 0005_perf_indexes
Revises: 0004_embeddings
Create Date: 2026-06-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_perf_indexes"
down_revision: Union[str, None] = "0004_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Latest-score lookups (DISTINCT ON / max(id) per article_id, on a table that
    # grows as re-scoring appends rows). Composite covers the article_id-only
    # filter too, so the old single-column index is redundant.
    op.create_index("ix_scores_article_id_id", "scores", ["article_id", "id"])
    op.drop_index("ix_scores_article_id", table_name="scores")

    # Corroboration window scan filters on coalesce(published_at, created_at)
    # within +/- window_hours; an expression index turns that into a range scan.
    op.create_index(
        "ix_articles_event_ts",
        "articles",
        [sa.text("coalesce(published_at, created_at)")],
    )

    # Hot worker/corroboration filters.
    op.create_index("ix_articles_extraction_status", "articles", ["extraction_status"])
    op.create_index("ix_articles_source_id", "articles", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_articles_source_id", table_name="articles")
    op.drop_index("ix_articles_extraction_status", table_name="articles")
    op.drop_index("ix_articles_event_ts", table_name="articles")
    op.create_index("ix_scores_article_id", "scores", ["article_id"])
    op.drop_index("ix_scores_article_id_id", table_name="scores")
