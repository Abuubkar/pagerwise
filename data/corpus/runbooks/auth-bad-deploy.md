---
service: auth
updated_at: 2026-02-28
---
# Auth: regression after a deploy

Alert: `AuthPostDeployErrors` fires when errors in the 30 minutes after a deploy, `auth_post_deploy_error_pct`, exceed their threshold. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Config drift.** The release expects a setting that isn't present in production.
- **Code regression.** The new release breaks a path the tests don't cover.

The most common cause on auth is schema mismatch: it explained 11 of the
last 16 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "schema mismatch" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-DEPLOY-419
   ```

4. If `auth_post_deploy_error_pct` stays above 8 for 12 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback auth`; don't wait to debug.
2. Freeze deploys for auth.
3. If that doesn't help within 10 minutes, set `canary_error_threshold_pct=11` on
   auth (`configctl set auth canary_error_threshold_pct 11`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 15 minutes without improvement, or at once if more than
10% of auth requests are failing. Coordinate in `#identity-oncall`.
