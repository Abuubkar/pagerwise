---
service: card-auth
updated_at: 2026-09-24
---
# Card auth: connection pool exhaustion

Alert: `CardAuthPoolExhausted` fires when the time requests wait for a database connection, `card_auth_pool_wait_ms`, stays above its threshold for 3 minutes. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on card-auth is pool too small for the replica count: it explained 14 of the
last 21 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-POOL-552
   ```

4. If `card_auth_pool_wait_ms` stays above 274 for 10 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `card-authctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/card-auth --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on redis-cache.
3. If that doesn't help within 10 minutes, set `pool_checkout_timeout_ms=60` on
   card-auth (`configctl set card-auth pool_checkout_timeout_ms 60`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 30 minutes without improvement, or at once if more than
5% of card-auth requests are failing. Coordinate in `#payments-oncall`.
