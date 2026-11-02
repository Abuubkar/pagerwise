---
service: inventory
updated_at: 2025-09-30
---
# Inventory: connection pool exhaustion

Alert: `InventoryPoolExhausted` fires when the time requests wait for a database connection, `inventory_pool_wait_ms`, stays above its threshold for 3 minutes. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on inventory is pool too small for the replica count: it explained 23 of the
last 25 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-POOL-526
   ```

4. If `inventory_pool_wait_ms` stays above 389 for 5 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `inventoryctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/inventory --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on postgres-primary.
3. If that doesn't help within 10 minutes, set `pool_checkout_timeout_ms=410` on
   inventory (`configctl set inventory pool_checkout_timeout_ms 410`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 15 minutes without improvement, or at once if more than
20% of inventory requests are failing. Coordinate in `#discovery-oncall`.
