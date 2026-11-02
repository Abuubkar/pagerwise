"""alert_events and dead_letters

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("service", sa.String(128), nullable=False, index=True),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("labels", JSONB(), server_default="{}", nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("severity IN ('critical', 'warning', 'info')", name="ck_alert_events_severity"),
    )

    op.create_table(
        "dead_letters",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), primary_key=True),
        sa.Column("original_topic", sa.String(255), nullable=False),
        sa.Column("original_partition", sa.Integer(), nullable=False),
        sa.Column("original_offset", sa.BigInteger(), nullable=False),
        sa.Column("dlq_offset", sa.BigInteger(), nullable=False, index=True),
        sa.Column("key", sa.String(255), nullable=True, index=True),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("headers", JSONB(), server_default="{}", nullable=False),
        sa.Column("error_class", sa.String(128), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_count", sa.Integer(), server_default="0", nullable=False),
        # A message redelivered after a crash is dead-lettered again; this keeps it to one row.
        sa.UniqueConstraint("original_topic", "original_partition", "original_offset"),
    )


def downgrade() -> None:
    op.drop_table("dead_letters")
    op.drop_table("alert_events")
