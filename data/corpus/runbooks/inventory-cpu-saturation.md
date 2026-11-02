---
service: inventory
updated_at: 2026-06-25
---
# Inventory: CPU saturation

Alert: `InventoryCPUSaturated` fires when CPU utilisation, `inventory_cpu_util_pct`, stays above its threshold for 10 minutes. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Traffic spike.** Legitimate load above what the current replica count serves.
- **Hot loop in a release.** A recent change made a common path far more expensive.

The most common cause on inventory is noisy neighbour: it explained 14 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "noisy neighbour" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-CPU-388
   ```

4. If `inventory_cpu_util_pct` stays above 82 for 5 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `cache_ttl_s=14` on
   inventory (`configctl set inventory cache_ttl_s 14`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 20 minutes without improvement, or at once if more than
5% of inventory requests are failing. Coordinate in `#discovery-oncall`.
