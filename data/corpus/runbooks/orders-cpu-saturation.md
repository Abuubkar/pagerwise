---
service: orders
updated_at: 2026-08-28
---
# Orders: CPU saturation

Alert: `OrdersCPUSaturated` fires when CPU utilisation, `orders_cpu_util_pct`, stays above its threshold for 10 minutes. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Traffic spike.** Legitimate load above what the current replica count serves.
- **Hot loop in a release.** A recent change made a common path far more expensive.

The most common cause on orders is noisy neighbour: it explained 9 of the
last 17 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "noisy neighbour" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-CPU-168
   ```

4. If `orders_cpu_util_pct` stays above 80 for 5 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `autoscale_max_replicas=26` on
   orders (`configctl set orders autoscale_max_replicas 26`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 45 minutes without improvement, or at once if more than
20% of orders requests are failing. Coordinate in `#commerce-oncall`.
