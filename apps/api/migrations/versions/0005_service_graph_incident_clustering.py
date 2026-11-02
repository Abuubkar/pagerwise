"""service graph, incident clustering columns, alert_events.incident_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("team", sa.String(64), nullable=False),
    )
    op.create_table(
        "service_edges",
        # caller -> callee: from_service depends on to_service.
        sa.Column("from_service", sa.String(128), sa.ForeignKey("services.name", ondelete="CASCADE"), primary_key=True),
        sa.Column("to_service", sa.String(128), sa.ForeignKey("services.name", ondelete="CASCADE"), primary_key=True),
        sa.CheckConstraint("from_service <> to_service", name="ck_service_edges_no_self"),
    )

    op.add_column("incidents", sa.Column("alert_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("incidents", sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True))
    # Embedding of the alert summary that opened the incident; new alerts are compared with it.
    op.add_column("incidents", sa.Column("embedding", VECTOR(384), nullable=True))
    op.create_index("ix_incidents_open_last_alert", "incidents", ["service", "last_alert_at"],
                    postgresql_where=sa.text("status <> 'resolved'"))

    op.add_column("alert_events", sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=True))
    op.create_index("ix_alert_events_incident_id", "alert_events", ["incident_id"])
    # Clustering's first question: has this service + fingerprint fired in the last 10 minutes, and into what?
    op.create_index("ix_alert_events_service_fingerprint_occurred", "alert_events",
                    ["service", "fingerprint", sa.text("occurred_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_alert_events_service_fingerprint_occurred", table_name="alert_events")
    op.drop_index("ix_alert_events_incident_id", table_name="alert_events")
    op.drop_column("alert_events", "incident_id")
    op.drop_index("ix_incidents_open_last_alert", table_name="incidents")
    op.drop_column("incidents", "embedding")
    op.drop_column("incidents", "last_alert_at")
    op.drop_column("incidents", "alert_count")
    op.drop_table("service_edges")
    op.drop_table("services")
