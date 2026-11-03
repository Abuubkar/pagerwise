"""Add triage_runs.traceparent: the trace context of the consumer batch that queued the run (docs/adr/0012)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-03

The triage worker's span links to it, so a brief's trace leads back to the alerts that opened its incident. Nullable,
no default: adding it is a catalog-only change, and runs queued by the API (or before this column) just have none.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '2s'")
    op.add_column("triage_runs", sa.Column("traceparent", sa.String(64), nullable=True))


def downgrade() -> None:
    op.execute("SET lock_timeout = '2s'")
    op.drop_column("triage_runs", "traceparent")
