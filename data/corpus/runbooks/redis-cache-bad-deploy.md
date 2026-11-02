---
service: redis-cache
updated_at: 2026-09-15
---
# Redis cache: regression after a deploy

Alert: `RedisCachePostDeployErrors` fires when errors in the 30 minutes after a deploy, `redis_cache_post_deploy_error_pct`, exceed their threshold. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Config drift.** The release expects a setting that isn't present in production.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Code regression.** The new release breaks a path the tests don't cover.

The most common cause on redis-cache is config drift: it explained 10 of the
last 15 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "config drift" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-DEPLOY-877
   ```

4. If `redis_cache_post_deploy_error_pct` stays above 8 for 8 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback redis-cache`; don't wait to debug.
2. Freeze deploys for redis-cache.
3. If that doesn't help within 10 minutes, set `deploy_batch_size=29` on
   redis-cache (`configctl set redis-cache deploy_batch_size 29`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
5% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
