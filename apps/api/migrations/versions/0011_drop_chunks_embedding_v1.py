"""Drop chunks.embedding (v1, bge-small) and its HNSW index: retrieval reads embedding_v2 only (docs/adr/0010)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-03

Run only after the code that no longer reads or writes it is deployed (docs/migrations.md). The index goes first,
CONCURRENTLY, so readers and writers keep going; dropping the column then only takes a brief lock. Incidents keep
their own bge-small embedding (incidents.embedding) for clustering; that column isn't touched.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("SET lock_timeout = '2s'")
    op.drop_column("chunks", "embedding")


def downgrade() -> None:
    # Brings the column back empty: v1 vectors are gone. Re-importing with the pre-6b code refills them.
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(384)")
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chunks_embedding_hnsw "
                   "ON chunks USING hnsw (embedding vector_cosine_ops)")
