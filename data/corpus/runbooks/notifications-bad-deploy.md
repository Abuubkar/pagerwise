---
service: notifications
updated_at: 2026-10-14
---
# Notifications: regression after a deploy

Alert: `NotificationsPostDeployErrors` fires when errors in the 30 minutes after a deploy, `notifications_post_deploy_error_pct`, exceed their threshold. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Code regression.** The new release breaks a path the tests don't cover.
- **Config drift.** The release expects a setting that isn't present in production.

The most common cause on notifications is schema mismatch: it explained 23 of the
last 23 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "schema mismatch" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-DEPLOY-333
   ```

4. If `notifications_post_deploy_error_pct` stays above 2 for 7 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback notifications`; don't wait to debug.
2. Freeze deploys for notifications.
3. If that doesn't help within 10 minutes, set `feature_flag_default=29` on
   notifications (`configctl set notifications feature_flag_default 29`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 30 minutes without improvement, or at once if more than
25% of notifications requests are failing. Coordinate in `#growth-oncall`.
