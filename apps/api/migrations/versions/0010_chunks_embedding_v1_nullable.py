"""chunks.embedding (v1, bge-small) nullable: step 1 of dropping it (docs/migrations.md)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-03

Code from slice 6b on no longer writes chunks.embedding; until 0011 drops it, rows the importer inserts leave it
NULL. Dropping NOT NULL is a catalog change only (no table scan), so writers barely notice.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '2s'")
    op.alter_column("chunks", "embedding", nullable=True)


def downgrade() -> None:
    # Refuses (NOT NULL violation) if rows written since have no v1 embedding: re-import them with the old code first.
    op.alter_column("chunks", "embedding", nullable=False)
