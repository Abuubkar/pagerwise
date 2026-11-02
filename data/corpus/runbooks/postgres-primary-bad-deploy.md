---
service: postgres-primary
updated_at: 2026-07-16
---
# Postgres primary: regression after a deploy

Alert: `PostgresPrimaryPostDeployErrors` fires when errors in the 30 minutes after a deploy, `postgres_primary_post_deploy_error_pct`, exceed their threshold. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Code regression.** The new release breaks a path the tests don't cover.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Config drift.** The release expects a setting that isn't present in production.

The most common cause on postgres-primary is code regression: it explained 14 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "code regression" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-DEPLOY-939
   ```

4. If `postgres_primary_post_deploy_error_pct` stays above 8 for 4 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback postgres-primary`; don't wait to debug.
2. Freeze deploys for postgres-primary.
3. If that doesn't help within 10 minutes, set `feature_flag_default=63` on
   postgres-primary (`configctl set postgres-primary feature_flag_default 63`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 15 minutes without improvement, or at once if more than
5% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
