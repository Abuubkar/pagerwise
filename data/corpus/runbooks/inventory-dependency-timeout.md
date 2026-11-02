---
service: inventory
updated_at: 2026-08-01
---
# Inventory: dependency timeouts

Alert: `InventoryUpstreamTimeouts` fires when the share of calls to a dependency that time out, `inventory_upstream_timeout_pct`, stays above its threshold for 5 minutes. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- Timeouts concentrate on calls to postgres-primary.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Network path.** Packet loss between zones adds retransmits.
- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Dependency degraded.** postgres-primary itself is slow or partially down.

The most common cause on inventory is network path: it explained 20 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "network path" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-DEP-714
   ```

4. If `inventory_upstream_timeout_pct` stays above 1 for 6 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check postgres-primary's own dashboard before changing anything in inventory.

## Mitigation

1. Open the circuit breaker for postgres-primary if the feature can degrade.
2. Fail over calls to the standby region for postgres-primary if one exists.
3. If that doesn't help within 10 minutes, set `retry_max_attempts=14` on
   inventory (`configctl set inventory retry_max_attempts 14`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 30 minutes without improvement, or at once if more than
5% of inventory requests are failing. Coordinate in `#discovery-oncall`.
