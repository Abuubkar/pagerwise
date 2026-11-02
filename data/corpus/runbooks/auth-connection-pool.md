---
service: auth
updated_at: 2026-06-09
---
# Auth: connection pool exhaustion

Alert: `AuthPoolExhausted` fires when the time requests wait for a database connection, `auth_pool_wait_ms`, stays above its threshold for 3 minutes. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on auth is pool too small for the replica count: it explained 9 of the
last 16 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-POOL-112
   ```

4. If `auth_pool_wait_ms` stays above 387 for 6 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `authctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/auth --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on redis-cache.
3. If that doesn't help within 10 minutes, set `pool_checkout_timeout_ms=550` on
   auth (`configctl set auth pool_checkout_timeout_ms 550`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 20 minutes without improvement, or at once if more than
25% of auth requests are failing. Coordinate in `#identity-oncall`.
