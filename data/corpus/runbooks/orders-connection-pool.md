---
service: orders
updated_at: 2025-10-01
---
# Orders: connection pool exhaustion

Alert: `OrdersPoolExhausted` fires when the time requests wait for a database connection, `orders_pool_wait_ms`, stays above its threshold for 3 minutes. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on orders is long transactions holding connections: it explained 14 of the
last 22 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "long transactions holding connections" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-POOL-940
   ```

4. If `orders_pool_wait_ms` stays above 583 for 4 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `ordersctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/orders --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on payments.
3. If that doesn't help within 10 minutes, set `pool_max_size=27` on
   orders (`configctl set orders pool_max_size 27`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 20 minutes without improvement, or at once if more than
5% of orders requests are failing. Coordinate in `#commerce-oncall`.
