"""add scores.corroboration evidence column (Phase 2)

Revision ID: 0002_corroboration
Revises: 0001_initial
Create Date: 2026-06-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_corroboration"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # corroboration_subscore already exists (reserved since 0001); this adds the
    # human-inspectable evidence (which other-source articles matched the event).
    op.add_column(
        "scores",
        sa.Column("corroboration", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scores", "corroboration")
