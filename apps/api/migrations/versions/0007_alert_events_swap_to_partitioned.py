"""alert_events, step 2 of 2: swap the partitioned shadow in (after scripts/backfill_partitions.py)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02

One short transaction. Waits at most 2 s for its lock (retrying up to 10 times rather than queueing behind a long
query, which would block every writer queued behind it), refuses to swap unless both tables hold the same number
of rows, then renames: alert_events -> alert_events_old, alert_events_p -> alert_events. The old table stays for
rollback (docs/migrations.md) until a later migration drops it.
"""

import time
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import OperationalError

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = ["incident_id", "occurred_at", "service", "service_fingerprint_occurred"]


def _lock(conn: sa.Connection, tables: str) -> None:
    conn.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
    for attempt in range(1, 11):
        try:
            with conn.begin_nested():  # a lock taken in a released savepoint stays with the transaction
                conn.execute(sa.text(f"LOCK TABLE {tables} IN ACCESS EXCLUSIVE MODE"))
            return
        except OperationalError:
            if attempt == 10:
                raise
            time.sleep(attempt * 0.5)


def upgrade() -> None:
    conn = op.get_bind()
    _lock(conn, "alert_events, alert_events_p")
    old = conn.scalar(sa.text("SELECT count(*) FROM alert_events"))
    new = conn.scalar(sa.text("SELECT count(*) FROM alert_events_p"))
    if old != new:
        raise RuntimeError(f"alert_events has {old} rows and alert_events_p {new}: run "
                           "scripts/backfill_partitions.py until it finishes, then upgrade again")
    statements = [
        "DROP TRIGGER alert_events_mirror ON alert_events",
        "DROP FUNCTION alert_events_mirror()",
        "ALTER TABLE alert_events RENAME TO alert_events_old",
        "ALTER TABLE alert_events_old RENAME CONSTRAINT alert_events_pkey TO alert_events_old_pkey",
        ("ALTER TABLE alert_events_old RENAME CONSTRAINT alert_events_incident_id_fkey "
        "TO alert_events_old_incident_id_fkey"),
        "ALTER INDEX ix_alert_events_occurred_event RENAME TO ix_alert_events_old_occurred_event",
        *[f"ALTER INDEX ix_alert_events_{i} RENAME TO ix_alert_events_old_{i}" for i in INDEXES],
        "ALTER TABLE alert_events_p RENAME TO alert_events",
        "ALTER TABLE alert_events RENAME CONSTRAINT alert_events_p_pkey TO alert_events_pkey",
        "ALTER TABLE alert_events RENAME CONSTRAINT alert_events_p_incident_id_fkey TO alert_events_incident_id_fkey",
        *[f"ALTER INDEX ix_alert_events_p_{i} RENAME TO ix_alert_events_{i}" for i in INDEXES],
    ]
    for statement in statements:
        conn.execute(sa.text(statement))


def downgrade() -> None:
    """Swaps back. Rows written since the swap exist only in the partitioned table, so they're copied into the old
    one first; then the mirror trigger is restored so migration 0006's state is complete again."""
    conn = op.get_bind()
    _lock(conn, "alert_events, alert_events_old")
    conn.execute(sa.text("INSERT INTO alert_events_old SELECT * FROM alert_events ON CONFLICT DO NOTHING"))
    statements = [
        *[f"ALTER INDEX ix_alert_events_{i} RENAME TO ix_alert_events_p_{i}" for i in INDEXES],
        "ALTER TABLE alert_events RENAME CONSTRAINT alert_events_incident_id_fkey TO alert_events_p_incident_id_fkey",
        "ALTER TABLE alert_events RENAME CONSTRAINT alert_events_pkey TO alert_events_p_pkey",
        "ALTER TABLE alert_events RENAME TO alert_events_p",
        *[f"ALTER INDEX ix_alert_events_old_{i} RENAME TO ix_alert_events_{i}" for i in INDEXES],
        "ALTER INDEX ix_alert_events_old_occurred_event RENAME TO ix_alert_events_occurred_event",
        ("ALTER TABLE alert_events_old RENAME CONSTRAINT alert_events_old_incident_id_fkey "
        "TO alert_events_incident_id_fkey"),
        "ALTER TABLE alert_events_old RENAME CONSTRAINT alert_events_old_pkey TO alert_events_pkey",
        "ALTER TABLE alert_events_old RENAME TO alert_events",
    ]
    for statement in statements:
        conn.execute(sa.text(statement))
    # Same as migration 0006's MIRROR (migration files are frozen copies, so it's repeated rather than imported).
    conn.execute(sa.text("""
        CREATE FUNCTION alert_events_mirror() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                DELETE FROM alert_events_p WHERE event_id = OLD.event_id AND occurred_at = OLD.occurred_at;
            END IF;
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                INSERT INTO alert_events_p SELECT NEW.* ON CONFLICT DO NOTHING;
            END IF;
            RETURN NULL;
        END $$
    """))
    conn.execute(sa.text("CREATE TRIGGER alert_events_mirror AFTER INSERT OR UPDATE OR DELETE ON alert_events "
                         "FOR EACH ROW EXECUTE FUNCTION alert_events_mirror()"))
