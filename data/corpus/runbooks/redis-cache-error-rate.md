---
service: redis-cache
updated_at: 2026-03-26
---
# Redis cache: elevated error rate

Alert: `RedisCacheErrorRateHigh` fires when the share of 5xx responses in `redis_cache_error_ratio_pct` stays above its threshold for 5 minutes. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Dependency errors passed through.** its database returns errors and the service doesn't degrade.
- **Bad deploy.** A recent release introduced an exception on a common path.
- **Expired credentials.** A rotated secret wasn't picked up and calls to its database are rejected.

The most common cause on redis-cache is dependency errors passed through: it explained 14 of the
last 19 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "dependency errors passed through" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-ERR-166
   ```

4. If `redis_cache_error_ratio_pct` stays above 6 for 8 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback redis-cache`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=26` on
   redis-cache (`configctl set redis-cache circuit_breaker_threshold 26`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 15 minutes without improvement, or at once if more than
20% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
