---
service: orders
updated_at: 2026-05-25
---
# Orders: high p99 latency

Alert: `OrdersLatencyHigh` fires when the p99 of `orders_p99_latency_ms` stays above its threshold for 5 minutes. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on payments grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Slow dependency.** Most latency is spent waiting on payments; check its own latency first.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.

The most common cause on orders is slow dependency: it explained 9 of the
last 9 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "slow dependency" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-LAT-519
   ```

4. If `orders_p99_latency_ms` stays above 2024 for 7 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on payments.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed orders --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `worker_threads=44` on
   orders (`configctl set orders worker_threads 44`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 30 minutes without improvement, or at once if more than
25% of orders requests are failing. Coordinate in `#commerce-oncall`.
