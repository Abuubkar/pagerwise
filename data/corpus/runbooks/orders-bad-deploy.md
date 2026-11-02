---
service: orders
updated_at: 2026-04-15
---
# Orders: regression after a deploy

Alert: `OrdersPostDeployErrors` fires when errors in the 30 minutes after a deploy, `orders_post_deploy_error_pct`, exceed their threshold. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Code regression.** The new release breaks a path the tests don't cover.
- **Config drift.** The release expects a setting that isn't present in production.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.

The most common cause on orders is code regression: it explained 10 of the
last 11 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "code regression" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-DEPLOY-675
   ```

4. If `orders_post_deploy_error_pct` stays above 4 for 3 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback orders`; don't wait to debug.
2. Freeze deploys for orders.
3. If that doesn't help within 10 minutes, set `feature_flag_default=4` on
   orders (`configctl set orders feature_flag_default 4`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 45 minutes without improvement, or at once if more than
20% of orders requests are failing. Coordinate in `#commerce-oncall`.
