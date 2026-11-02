"""deploys, import_state, document source timestamps, full-text and HNSW indexes on chunks

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deploys",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), primary_key=True),
        sa.Column("service", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author", sa.String(128), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("status IN ('succeeded', 'rolled_back')", name="ck_deploys_status"),
    )
    op.create_index("ix_deploys_service_deployed_at", "deploys", ["service", sa.text("deployed_at DESC")])

    op.create_table(
        "import_state",
        sa.Column("source", sa.String(64), primary_key=True),  # a docs API collection, e.g. runbooks
        # The page to fetch next if a run stopped partway; NULL once a listing has completed.
        sa.Column("next_url", sa.Text(), nullable=True),
        # updated_at of the last document stored; a listing restarted after its cursor expired asks for since=this.
        sa.Column("resume_since", sa.DateTime(timezone=True), nullable=True),
        # page URL -> {"etag", "next"}: lets the next run send If-None-Match and still know the next page on a 304.
        sa.Column("pages", JSONB(), server_default="{}", nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("documents", sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True))

    # Full-text search over the same text that is embedded: heading path, then body.
    op.add_column(
        "chunks",
        sa.Column(
            "tsv",
            TSVECTOR(),
            sa.Computed("to_tsvector('english', heading_path || ' ' || text)", persisted=True),
            nullable=False,
        ),
    )
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    # pgvector defaults (m=16, ef_construction=64); cosine, matching the <=> queries.
    op.create_index(
        "ix_chunks_embedding_hnsw", "chunks", ["embedding"], postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_column("chunks", "tsv")
    op.drop_column("documents", "source_updated_at")
    op.drop_table("import_state")
    op.drop_table("deploys")
