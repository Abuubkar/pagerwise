---
service: inventory
updated_at: 2026-03-21
---
# Inventory: memory pressure and OOM kills

Alert: `InventoryMemoryPressure` fires when container memory, `inventory_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Large payloads.** A few very large requests allocate far more than usual.
- **Memory leak in a recent release.** A new code path keeps references to finished requests.

The most common cause on inventory is unbounded cache: it explained 9 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "unbounded cache" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-MEM-680
   ```

4. If `inventory_rss_pct_of_limit` stays above 89 for 7 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/inventory`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `max_request_body_kb=25` on
   inventory (`configctl set inventory max_request_body_kb 25`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 20 minutes without improvement, or at once if more than
10% of inventory requests are failing. Coordinate in `#discovery-oncall`.
