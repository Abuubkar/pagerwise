---
service: redis-cache
updated_at: 2026-10-06
---
# Redis cache: memory pressure and OOM kills

Alert: `RedisCacheMemoryPressure` fires when container memory, `redis_cache_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Large payloads.** A few very large requests allocate far more than usual.

The most common cause on redis-cache is memory leak in a recent release: it explained 9 of the
last 10 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "memory leak in a recent release" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-MEM-129
   ```

4. If `redis_cache_rss_pct_of_limit` stays above 91 for 10 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/redis-cache`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `gc_target_pct=27` on
   redis-cache (`configctl set redis-cache gc_target_pct 27`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
10% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
