---
service: inventory
updated_at: 2026-10-14
---
# Inventory: high p99 latency

Alert: `InventoryLatencyHigh` fires when the p99 of `inventory_p99_latency_ms` stays above its threshold for 5 minutes. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on postgres-primary grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Slow dependency.** Most latency is spent waiting on postgres-primary; check its own latency first.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.

The most common cause on inventory is garbage collection pauses: it explained 22 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "garbage collection pauses" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-LAT-501
   ```

4. If `inventory_p99_latency_ms` stays above 1648 for 6 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on postgres-primary.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed inventory --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `request_timeout_ms=170` on
   inventory (`configctl set inventory request_timeout_ms 170`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 30 minutes without improvement, or at once if more than
10% of inventory requests are failing. Coordinate in `#discovery-oncall`.
