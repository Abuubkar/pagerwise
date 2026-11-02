# Data migrations

## alert_events: plain table to daily partitions, online (migrations 0006 and 0007)

**Why.** alert_events grows by millions of rows a day in a storm. Partitioning by day on `occurred_at` lets a query
for the last 7 days read 8 small tables instead of one huge one (partition pruning), and lets old days be dropped
whole instead of deleted row by row. A unique key on a partitioned table must include the partition key, so the
primary key becomes `(event_id, occurred_at)`; inserts use `ON CONFLICT DO NOTHING` without naming the key, so the
consumer works before, during and after the change.

**The procedure.** Writers (the consumer) keep running throughout.

```bash
uv run alembic upgrade 0006                    # 1. shadow table + mirror trigger
uv run python scripts/backfill_partitions.py   # 2. copy existing rows; safe to stop and rerun
uv run alembic upgrade 0007                    # 3. check counts, swap names (one short transaction)
```

1. **0006** creates `alert_events_p` (`LIKE alert_events`, `PARTITION BY RANGE (occurred_at)`), a `DEFAULT`
   partition, daily partitions from the oldest row to 7 days ahead (`create_alert_partitions(days_ahead,
   days_back, parent)`), and an `AFTER INSERT OR UPDATE OR DELETE` trigger on `alert_events` that mirrors each row
   change into the shadow. It also builds `(occurred_at, event_id)` on the old table `CONCURRENTLY` for the backfill.
   The shadow's foreign key and the trigger need locks on `incidents` and `alert_events`, which the consumer writes
   in either order, so 0006 takes both together with `lock_timeout = 500ms` and retries (below the 1 s deadlock
   check, so it backs off instead of a writer being killed). Writers wait for that lock for milliseconds.
2. **The backfill** walks the old table in `(occurred_at, event_id)` order in 50k-row batches, one transaction
   each, inserting with `ON CONFLICT DO NOTHING` and saving its position in `alert_events_backfill`. It copies only
   up to the last row that existed when it started; later rows are already arriving through the trigger, which was
   created first, so no row can fall between the two.
3. **0007** sets `lock_timeout = 2s` and takes `ACCESS EXCLUSIVE` on both tables, retrying up to 10 times rather than
   waiting in the lock queue (a waiting `ACCESS EXCLUSIVE` request blocks every writer behind it). It refuses to
   continue unless both tables have the same row count. Then it drops the trigger and renames:
   `alert_events` -> `alert_events_old`, `alert_events_p` -> `alert_events`, with their constraints and indexes.
   Writers wait for this transaction (milliseconds plus two `count(*)`s) and then write to the partitioned table.

**Check it worked.**

```sql
SELECT relkind FROM pg_class WHERE relname = 'alert_events';            -- 'p'
SELECT (SELECT count(*) FROM alert_events_old) AS old, (SELECT count(*) FROM alert_events) AS new;
EXPLAIN SELECT count(*) FROM alert_events
 WHERE occurred_at >= now() - interval '7 days' AND occurred_at < now();  -- "Subplans Removed: N", 8 days + DEFAULT
```

**Keeping partitions ahead.** The consumer calls `create_alert_partitions(7)` at startup and every hour, so a week
of partitions always exists. A row with no partition for its day lands in `DEFAULT`; the next call that creates
that day's partition moves those rows into it before attaching it.

**Rollback.**
- *Before 0007:* `uv run alembic downgrade 0005` drops the shadow, the trigger and the backfill state. Nothing
  else changed.
- *After 0007, while `alert_events_old` still exists:* `uv run alembic downgrade 0006`. It locks both tables,
  copies rows written since the swap back into the old table (`ON CONFLICT DO NOTHING`), renames everything back
  and recreates the mirror trigger, so the old table is complete and the shadow keeps up again.
- *After `alert_events_old` is dropped:* no rollback by renaming; restore from a backup.

**Cleanup.** `alert_events_old` is kept for rollback. Drop it in a later migration once the partitioned table has
run for a while (planned: after slice 5). Until then it costs disk, nothing else: no writes reach it.

**Caveats.**
- Between 0006 and 0007, a column added to `alert_events` must also be added to `alert_events_p`: the trigger
  copies rows by column position.
- Nothing in the app updates or deletes alert_events. If something did during the backfill, a row the backfill read
  before a concurrent delete could be copied after the trigger's delete; the count check in 0007 would then refuse
  to swap (the shadow would have more rows), and the fix is to delete the extra rows and run 0007 again.
- Verified by `apps/api/tests/test_partition_swap_service.py`: 20k rows of history, a writer inserting one row per
  commit through 0006, the backfill and 0007; afterwards every row is present exactly once and a 7-day query scans 9
  of 30 partitions. With the backfill disabled, 0007 refuses to swap.
