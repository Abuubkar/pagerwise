---
service: card-auth
updated_at: 2026-01-30
---
# Card auth: regression after a deploy

Alert: `CardAuthPostDeployErrors` fires when errors in the 30 minutes after a deploy, `card_auth_post_deploy_error_pct`, exceed their threshold. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Code regression.** The new release breaks a path the tests don't cover.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Config drift.** The release expects a setting that isn't present in production.

The most common cause on card-auth is code regression: it explained 11 of the
last 12 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "code regression" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-DEPLOY-969
   ```

4. If `card_auth_post_deploy_error_pct` stays above 3 for 10 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback card-auth`; don't wait to debug.
2. Freeze deploys for card-auth.
3. If that doesn't help within 10 minutes, set `feature_flag_default=54` on
   card-auth (`configctl set card-auth feature_flag_default 54`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 45 minutes without improvement, or at once if more than
20% of card-auth requests are failing. Coordinate in `#payments-oncall`.
