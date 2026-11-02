"""chunks.embedding_v2: bge-base-en-v1.5 (768-d) next to bge-small's 384-d embedding, for a gated switch

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-02

Filled by scripts/reembed.py (resumable, throttled) and by the importer for new or changed documents. Retrieval
reads it when RETRIEVAL_EMBEDDING_VERSION is v2 or dual. The old column is dropped only if the eval says v2 is at
least as good (docs/adr/0009).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("embedding_v2", VECTOR(768), nullable=True))
    with op.get_context().autocommit_block():
        # CONCURRENTLY: writers to chunks (the importer) keep going while it builds.
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chunks_embedding_v2_hnsw "
                   "ON chunks USING hnsw (embedding_v2 vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_v2_hnsw")
    op.drop_column("chunks", "embedding_v2")
