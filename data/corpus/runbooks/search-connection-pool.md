---
service: search
updated_at: 2026-05-25
---
# Search: connection pool exhaustion

Alert: `SearchPoolExhausted` fires when the time requests wait for a database connection, `search_pool_wait_ms`, stays above its threshold for 3 minutes. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on search is long transactions holding connections: it explained 8 of the
last 9 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "long transactions holding connections" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-POOL-295
   ```

4. If `search_pool_wait_ms` stays above 319 for 8 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `searchctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/search --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on inventory.
3. If that doesn't help within 10 minutes, set `pool_max_size=43` on
   search (`configctl set search pool_max_size 43`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 30 minutes without improvement, or at once if more than
20% of search requests are failing. Coordinate in `#discovery-oncall`.
