"""add scores.topic column + index

Revision ID: 0003_topic
Revises: 0002_corroboration
Create Date: 2026-06-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_topic"
down_revision: Union[str, None] = "0002_corroboration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scores", sa.Column("topic", sa.String(length=32), nullable=True))
    op.create_index("ix_scores_topic", "scores", ["topic"])


def downgrade() -> None:
    op.drop_index("ix_scores_topic", table_name="scores")
    op.drop_column("scores", "topic")
