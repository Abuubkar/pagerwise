---
service: postgres-primary
---
# Postgres primary: replication lag

Alert: `PostgresReplicaLagHigh` fires when any replica of postgres-primary is more than 30 seconds behind for 5
minutes.

## Why it matters

Reporting and the read-only API read from replicas. Lag above 30 seconds means users see stale balances. More
importantly, automatic failover refuses to promote a replica that is more than 1 MB of WAL behind the leader
(`maximum_lag_on_failover = 1048576`), so heavy lag can leave the cluster with no failover candidate.

## Diagnosis

### Measure lag on the primary

```sql
SELECT application_name, state,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)) AS replay_lag_bytes,
       replay_lag
FROM pg_stat_replication;
```

### Common causes

- A long query on the replica conflicting with replay. Replicas use `max_standby_streaming_delay = 30s`, so replay
  can pause for up to 30 seconds behind a long read.
- A bulk write on the primary, such as a backfill or the nightly reconciliation, producing WAL faster than the
  replica can apply it.
- Disk saturation on the replica. Check `node_disk_io_time_seconds_total` for the replica host.

## First steps

1. Run the lag query and note which replica is behind and by how much.
2. If one replica lags and the others don't, look for long queries on that replica and cancel them.
3. If every replica lags, find the bulk writer on the primary and pause it; backfills accept `--pause`.
4. Do not trigger a manual failover while lag is above 1 MB: Patroni will refuse, and a forced promotion loses the
   unreplicated writes.

## Escalation

Page the database on-call if lag keeps growing for more than 15 minutes.
