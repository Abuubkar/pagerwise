---
service: ledger
updated_at: 2026-02-15
---
# Ledger: regression after a deploy

Alert: `LedgerPostDeployErrors` fires when errors in the 30 minutes after a deploy, `ledger_post_deploy_error_pct`, exceed their threshold. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Config drift.** The release expects a setting that isn't present in production.
- **Code regression.** The new release breaks a path the tests don't cover.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.

The most common cause on ledger is config drift: it explained 8 of the
last 15 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "config drift" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-DEPLOY-586
   ```

4. If `ledger_post_deploy_error_pct` stays above 7 for 4 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback ledger`; don't wait to debug.
2. Freeze deploys for ledger.
3. If that doesn't help within 10 minutes, set `deploy_batch_size=34` on
   ledger (`configctl set ledger deploy_batch_size 34`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 15 minutes without improvement, or at once if more than
20% of ledger requests are failing. Coordinate in `#ledger-oncall`.
