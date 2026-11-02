---
service: postgres-primary
updated_at: 2026-02-04
---
# Postgres primary: connection pool exhaustion

Alert: `PostgresPrimaryPoolExhausted` fires when the time requests wait for a database connection, `postgres_primary_pool_wait_ms`, stays above its threshold for 3 minutes. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on postgres-primary is pool too small for the replica count: it explained 16 of the
last 29 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-POOL-567
   ```

4. If `postgres_primary_pool_wait_ms` stays above 420 for 3 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `postgres-primaryctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/postgres-primary --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on its database.
3. If that doesn't help within 10 minutes, set `pool_max_size=49` on
   postgres-primary (`configctl set postgres-primary pool_max_size 49`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
20% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
