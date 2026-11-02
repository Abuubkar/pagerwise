---
service: search
updated_at: 2026-10-30
---
# Search: regression after a deploy

Alert: `SearchPostDeployErrors` fires when errors in the 30 minutes after a deploy, `search_post_deploy_error_pct`, exceed their threshold. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Code regression.** The new release breaks a path the tests don't cover.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Config drift.** The release expects a setting that isn't present in production.

The most common cause on search is code regression: it explained 10 of the
last 17 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "code regression" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-DEPLOY-864
   ```

4. If `search_post_deploy_error_pct` stays above 1 for 7 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback search`; don't wait to debug.
2. Freeze deploys for search.
3. If that doesn't help within 10 minutes, set `feature_flag_default=46` on
   search (`configctl set search feature_flag_default 46`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 15 minutes without improvement, or at once if more than
10% of search requests are failing. Coordinate in `#discovery-oncall`.
