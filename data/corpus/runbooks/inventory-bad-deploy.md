---
service: inventory
updated_at: 2026-07-19
---
# Inventory: regression after a deploy

Alert: `InventoryPostDeployErrors` fires when errors in the 30 minutes after a deploy, `inventory_post_deploy_error_pct`, exceed their threshold. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Code regression.** The new release breaks a path the tests don't cover.
- **Config drift.** The release expects a setting that isn't present in production.

The most common cause on inventory is schema mismatch: it explained 7 of the
last 9 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "schema mismatch" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-DEPLOY-322
   ```

4. If `inventory_post_deploy_error_pct` stays above 2 for 8 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback inventory`; don't wait to debug.
2. Freeze deploys for inventory.
3. If that doesn't help within 10 minutes, set `canary_error_threshold_pct=25` on
   inventory (`configctl set inventory canary_error_threshold_pct 25`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 15 minutes without improvement, or at once if more than
10% of inventory requests are failing. Coordinate in `#discovery-oncall`.
