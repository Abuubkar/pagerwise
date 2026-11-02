---
service: orders
updated_at: 2026-08-05
---
# Orders: memory pressure and OOM kills

Alert: `OrdersMemoryPressure` fires when container memory, `orders_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Large payloads.** A few very large requests allocate far more than usual.

The most common cause on orders is unbounded cache: it explained 15 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "unbounded cache" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-MEM-756
   ```

4. If `orders_rss_pct_of_limit` stays above 81 for 5 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/orders`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `max_request_body_kb=7` on
   orders (`configctl set orders max_request_body_kb 7`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 30 minutes without improvement, or at once if more than
20% of orders requests are failing. Coordinate in `#commerce-oncall`.
