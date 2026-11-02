---
service: redis-cache
updated_at: 2026-06-17
---
# Redis cache: connection pool exhaustion

Alert: `RedisCachePoolExhausted` fires when the time requests wait for a database connection, `redis_cache_pool_wait_ms`, stays above its threshold for 3 minutes. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on redis-cache is pool too small for the replica count: it explained 14 of the
last 15 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-POOL-954
   ```

4. If `redis_cache_pool_wait_ms` stays above 254 for 3 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `redis-cachectl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/redis-cache --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on its database.
3. If that doesn't help within 10 minutes, set `statement_timeout_ms=200` on
   redis-cache (`configctl set redis-cache statement_timeout_ms 200`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
10% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
