---
service: payments
updated_at: 2026-08-26
---
# Payments: regression after a deploy

Alert: `PaymentsPostDeployErrors` fires when errors in the 30 minutes after a deploy, `payments_post_deploy_error_pct`, exceed their threshold. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Code regression.** The new release breaks a path the tests don't cover.
- **Config drift.** The release expects a setting that isn't present in production.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.

The most common cause on payments is code regression: it explained 21 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "code regression" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-DEPLOY-569
   ```

4. If `payments_post_deploy_error_pct` stays above 1 for 8 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback payments`; don't wait to debug.
2. Freeze deploys for payments.
3. If that doesn't help within 10 minutes, set `feature_flag_default=39` on
   payments (`configctl set payments feature_flag_default 39`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 20 minutes without improvement, or at once if more than
5% of payments requests are failing. Coordinate in `#payments-oncall`.
