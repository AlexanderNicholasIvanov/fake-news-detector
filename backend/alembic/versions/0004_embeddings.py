"""add article_embeddings table (pgvector) for corroboration recall

Revision ID: 0004_embeddings
Revises: 0003_topic
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0004_embeddings"
down_revision: Union[str, None] = "0003_topic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# nomic-embed-text dimensionality (see config/scoring.yaml: corroboration.embedding_dim).
EMBED_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "article_embeddings",
        # one embedding per article -> article_id is the PK (1:1 with articles).
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("article_id"),
    )
    # HNSW cosine index for fast nearest-neighbour candidate search.
    op.create_index(
        "ix_article_embeddings_hnsw",
        "article_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_article_embeddings_hnsw", table_name="article_embeddings")
    op.drop_table("article_embeddings")
    # leave the `vector` extension installed; dropping it would cascade other usage.
