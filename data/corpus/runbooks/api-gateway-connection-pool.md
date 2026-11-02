---
service: api-gateway
updated_at: 2026-03-31
---
# Api gateway: connection pool exhaustion

Alert: `ApiGatewayPoolExhausted` fires when the time requests wait for a database connection, `api_gateway_pool_wait_ms`, stays above its threshold for 3 minutes. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on api-gateway is pool too small for the replica count: it explained 11 of the
last 17 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-POOL-150
   ```

4. If `api_gateway_pool_wait_ms` stays above 740 for 10 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `api-gatewayctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/api-gateway --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on auth.
3. If that doesn't help within 10 minutes, set `pool_max_size=4` on
   api-gateway (`configctl set api-gateway pool_max_size 4`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 15 minutes without improvement, or at once if more than
20% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
