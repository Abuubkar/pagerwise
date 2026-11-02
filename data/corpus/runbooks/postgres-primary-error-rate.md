---
service: postgres-primary
updated_at: 2026-02-01
---
# Postgres primary: elevated error rate

Alert: `PostgresPrimaryErrorRateHigh` fires when the share of 5xx responses in `postgres_primary_error_ratio_pct` stays above its threshold for 5 minutes. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Dependency errors passed through.** its database returns errors and the service doesn't degrade.
- **Expired credentials.** A rotated secret wasn't picked up and calls to its database are rejected.
- **Bad deploy.** A recent release introduced an exception on a common path.

The most common cause on postgres-primary is dependency errors passed through: it explained 25 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "dependency errors passed through" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-ERR-955
   ```

4. If `postgres_primary_error_ratio_pct` stays above 3 for 10 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback postgres-primary`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=37` on
   postgres-primary (`configctl set postgres-primary circuit_breaker_threshold 37`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
25% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
