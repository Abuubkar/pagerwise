---
service: orders
updated_at: 2026-05-01
---
# Orders: dependency timeouts

Alert: `OrdersUpstreamTimeouts` fires when the share of calls to a dependency that time out, `orders_upstream_timeout_pct`, stays above its threshold for 5 minutes. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- Timeouts concentrate on calls to payments.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Network path.** Packet loss between zones adds retransmits.
- **Dependency degraded.** payments itself is slow or partially down.
- **Timeout set too low.** A recent config change shortened the timeout below normal latency.

The most common cause on orders is network path: it explained 12 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "network path" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-DEP-678
   ```

4. If `orders_upstream_timeout_pct` stays above 8 for 5 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check payments's own dashboard before changing anything in orders.

## Mitigation

1. Open the circuit breaker for payments if the feature can degrade.
2. Fail over calls to the standby region for payments if one exists.
3. If that doesn't help within 10 minutes, set `upstream_timeout_ms=40` on
   orders (`configctl set orders upstream_timeout_ms 40`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 20 minutes without improvement, or at once if more than
10% of orders requests are failing. Coordinate in `#commerce-oncall`.
