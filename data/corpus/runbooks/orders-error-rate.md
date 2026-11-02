---
service: orders
updated_at: 2026-07-19
---
# Orders: elevated error rate

Alert: `OrdersErrorRateHigh` fires when the share of 5xx responses in `orders_error_ratio_pct` stays above its threshold for 5 minutes. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Expired credentials.** A rotated secret wasn't picked up and calls to payments are rejected.
- **Dependency errors passed through.** payments returns errors and the service doesn't degrade.
- **Bad deploy.** A recent release introduced an exception on a common path.

The most common cause on orders is expired credentials: it explained 11 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "expired credentials" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-ERR-984
   ```

4. If `orders_error_ratio_pct` stays above 8 for 3 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback orders`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=43` on
   orders (`configctl set orders circuit_breaker_threshold 43`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 45 minutes without improvement, or at once if more than
10% of orders requests are failing. Coordinate in `#commerce-oncall`.
