---
service: inventory
updated_at: 2026-03-30
---
# Inventory: elevated error rate

Alert: `InventoryErrorRateHigh` fires when the share of 5xx responses in `inventory_error_ratio_pct` stays above its threshold for 5 minutes. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Dependency errors passed through.** postgres-primary returns errors and the service doesn't degrade.
- **Expired credentials.** A rotated secret wasn't picked up and calls to postgres-primary are rejected.
- **Bad deploy.** A recent release introduced an exception on a common path.

The most common cause on inventory is dependency errors passed through: it explained 9 of the
last 11 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "dependency errors passed through" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-ERR-173
   ```

4. If `inventory_error_ratio_pct` stays above 8 for 4 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback inventory`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=41` on
   inventory (`configctl set inventory circuit_breaker_threshold 41`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 45 minutes without improvement, or at once if more than
10% of inventory requests are failing. Coordinate in `#discovery-oncall`.
