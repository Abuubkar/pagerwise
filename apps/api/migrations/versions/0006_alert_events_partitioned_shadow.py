"""alert_events, step 1 of 2: a day-partitioned shadow table kept in sync by a trigger

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02

The online partition migration (docs/migrations.md):
  0006 (this)  create alert_events_p, partitioned by day on occurred_at, with a DEFAULT partition and daily
               partitions covering the data; a trigger on alert_events mirrors every write into it.
  backfill     scripts/backfill_partitions.py copies the existing rows in resumable 50k-row batches.
  0007         one short transaction: check the row counts match, then swap the table names.
Writers keep writing to alert_events throughout; nothing waits longer than the swap's lock.
"""

import time
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import OperationalError

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Creates the daily partitions from days_back days ago to days_ahead days ahead (UTC days) that don't exist yet.
# Rows that landed in the DEFAULT partition for a day before it had a partition are moved into it first; a CHECK
# constraint matching the bound lets ATTACH skip scanning the new partition. A no-op if `parent` isn't partitioned,
# so the consumer can call it hourly before and after the swap.
CREATE_PARTITIONS = """
CREATE FUNCTION create_alert_partitions(days_ahead int, days_back int DEFAULT 0,
                                        parent regclass DEFAULT 'alert_events') RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    today date := (now() AT TIME ZONE 'UTC')::date;
    day date;
    lo timestamptz;
    part text;
    default_part text;
    created int := 0;
BEGIN
    IF (SELECT relkind FROM pg_class WHERE oid = parent) <> 'p' THEN
        RETURN 0;
    END IF;
    SELECT c.relname INTO default_part FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
     WHERE i.inhparent = parent AND pg_get_expr(c.relpartbound, c.oid) = 'DEFAULT';
    FOR day IN SELECT d::date FROM generate_series(today - days_back, today + days_ahead, interval '1 day') AS d LOOP
        part := 'alert_events_' || to_char(day, 'YYYYMMDD');
        CONTINUE WHEN to_regclass(part) IS NOT NULL;
        lo := day::timestamp AT TIME ZONE 'UTC';
        EXECUTE format('CREATE TABLE %I (LIKE %s INCLUDING DEFAULTS INCLUDING CONSTRAINTS)', part, parent);
        EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I CHECK (occurred_at >= %L AND occurred_at < %L)',
                       part, part || '_bound', lo, lo + interval '1 day');
        IF default_part IS NOT NULL THEN
            EXECUTE format('WITH moved AS (DELETE FROM %I WHERE occurred_at >= %L AND occurred_at < %L RETURNING *) '
                           'INSERT INTO %I SELECT * FROM moved', default_part, lo, lo + interval '1 day', part);
        END IF;
        EXECUTE format('ALTER TABLE %s ATTACH PARTITION %I FOR VALUES FROM (%L) TO (%L)',
                       parent, part, lo, lo + interval '1 day');
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', part, part || '_bound');
        created := created + 1;
    END LOOP;
    RETURN created;
END $$;
"""

# Column order matches because alert_events_p was created LIKE alert_events. A column added to one later must be
# added to both until the swap.
MIRROR_FUNCTION = """
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
"""
MIRROR_TRIGGER = """
CREATE TRIGGER alert_events_mirror AFTER INSERT OR UPDATE OR DELETE ON alert_events
    FOR EACH ROW EXECUTE FUNCTION alert_events_mirror()
"""


def _lock(conn: sa.Connection, tables: str, mode: str) -> None:
    conn.execute(sa.text("SET LOCAL lock_timeout = '500ms'"))
    for attempt in range(1, 21):
        try:
            with conn.begin_nested():  # a lock taken in a released savepoint stays with the transaction
                conn.execute(sa.text(f"LOCK TABLE {tables} IN {mode} MODE"))
            return
        except OperationalError:  # lock_timeout: let the writers through, then try again
            if attempt == 20:
                raise
            time.sleep(0.2 * attempt)


def upgrade() -> None:
    for statement in [  # one per call: asyncpg runs a single statement at a time
        ("CREATE TABLE alert_events_p (LIKE alert_events INCLUDING DEFAULTS INCLUDING CONSTRAINTS) "
        "PARTITION BY RANGE (occurred_at)"),
        # A unique key on a partitioned table must include the partition key.
        "ALTER TABLE alert_events_p ADD CONSTRAINT alert_events_p_pkey PRIMARY KEY (event_id, occurred_at)",
        "CREATE INDEX ix_alert_events_p_incident_id ON alert_events_p (incident_id)",
        "CREATE INDEX ix_alert_events_p_occurred_at ON alert_events_p (occurred_at)",
        "CREATE INDEX ix_alert_events_p_service ON alert_events_p (service)",
        ("CREATE INDEX ix_alert_events_p_service_fingerprint_occurred "
        "ON alert_events_p (service, fingerprint, occurred_at DESC)"),
        "CREATE TABLE alert_events_default PARTITION OF alert_events_p DEFAULT",
    ]:
        op.execute(statement)
    op.execute(CREATE_PARTITIONS)
    op.execute("""
        SELECT create_alert_partitions(
            7, coalesce((now() AT TIME ZONE 'UTC')::date - min(occurred_at AT TIME ZONE 'UTC')::date, 0),
            'alert_events_p')
        FROM alert_events
    """)
    op.execute("""
        CREATE TABLE alert_events_backfill (
            id int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            -- The last row to copy, fixed when the backfill starts; later rows reach the shadow through the trigger.
            upper_occurred_at timestamptz,
            upper_event_id uuid,
            last_occurred_at timestamptz,  -- keyset position: everything up to here is copied
            last_event_id uuid,
            rows_copied bigint NOT NULL DEFAULT 0,
            finished_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute(MIRROR_FUNCTION)

    # The foreign key locks incidents and the trigger locks alert_events (SHARE ROW EXCLUSIVE, which blocks writes).
    # The consumer writes both tables in either order (a new incident is inserted before its alerts, a joined one
    # updated after), so no lock order is safe against it; the first version deadlocked with it. Instead, take both
    # locks together and give up after 500 ms, before Postgres's 1 s deadlock check would kill a writer's
    # transaction, and retry. Everything slow (the tables, 40-odd partitions) is already done, so they're held only
    # for the two statements below.
    _lock(op.get_bind(), "alert_events, incidents", "SHARE ROW EXCLUSIVE")
    op.execute("ALTER TABLE alert_events_p ADD CONSTRAINT alert_events_p_incident_id_fkey "
               "FOREIGN KEY (incident_id) REFERENCES incidents (id)")
    # The trigger starts mirroring before the backfill starts copying, so no row can fall between the two.
    op.execute(MIRROR_TRIGGER)
    with op.get_context().autocommit_block():
        # The backfill walks alert_events in (occurred_at, event_id) order. CONCURRENTLY doesn't block writers.
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_alert_events_occurred_event "
                   "ON alert_events (occurred_at, event_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_alert_events_occurred_event")
    op.execute("DROP TRIGGER IF EXISTS alert_events_mirror ON alert_events")
    op.execute("DROP FUNCTION IF EXISTS alert_events_mirror()")
    op.execute("DROP TABLE IF EXISTS alert_events_backfill")
    op.execute("DROP TABLE IF EXISTS alert_events_p CASCADE")
    op.execute("DROP FUNCTION IF EXISTS create_alert_partitions(int, int, regclass)")
