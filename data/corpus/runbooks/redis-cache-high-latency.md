---
service: redis-cache
updated_at: 2026-08-31
---
# Redis cache: high p99 latency

Alert: `RedisCacheLatencyHigh` fires when the p99 of `redis_cache_p99_latency_ms` stays above its threshold for 5 minutes. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on its database grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Slow dependency.** Most latency is spent waiting on its database; check its own latency first.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.

The most common cause on redis-cache is slow dependency: it explained 14 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "slow dependency" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-LAT-223
   ```

4. If `redis_cache_p99_latency_ms` stays above 1370 for 8 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on its database.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed redis-cache --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `worker_threads=2` on
   redis-cache (`configctl set redis-cache worker_threads 2`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 15 minutes without improvement, or at once if more than
20% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
