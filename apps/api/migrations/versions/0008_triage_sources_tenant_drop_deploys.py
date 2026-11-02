"""triage_runs.degraded_sources and tenant; drop deploys (served over HTTP by the deploy source now)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Evidence sources that failed or timed out for this run: [{"source", "reason"}]. The brief must not assert
    # anything about them.
    op.add_column("triage_runs", sa.Column("degraded_sources", JSONB(), server_default="[]", nullable=False))
    # Whose concurrency budget the run counts against (the X-Pagerwise-Tenant header; 'default' for auto-started).
    op.add_column("triage_runs", sa.Column("tenant", sa.String(64), server_default="default", nullable=False))
    # Nothing reads it: triage fetches deploys from the deploy source (docs_mock's /v1/deploys) at run time.
    op.drop_table("deploys")


def downgrade() -> None:
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
    op.drop_column("triage_runs", "tenant")
    op.drop_column("triage_runs", "degraded_sources")
