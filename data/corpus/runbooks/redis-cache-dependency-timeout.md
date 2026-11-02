---
service: redis-cache
updated_at: 2026-02-17
---
# Redis cache: dependency timeouts

Alert: `RedisCacheUpstreamTimeouts` fires when the share of calls to a dependency that time out, `redis_cache_upstream_timeout_pct`, stays above its threshold for 5 minutes. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- Timeouts concentrate on calls to its database.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Network path.** Packet loss between zones adds retransmits.
- **Dependency degraded.** its database itself is slow or partially down.

The most common cause on redis-cache is timeout set too low: it explained 14 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "timeout set too low" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-DEP-222
   ```

4. If `redis_cache_upstream_timeout_pct` stays above 9 for 10 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check its database's own dashboard before changing anything in redis-cache.

## Mitigation

1. Open the circuit breaker for its database if the feature can degrade.
2. Fail over calls to the standby region for its database if one exists.
3. If that doesn't help within 10 minutes, set `upstream_timeout_ms=430` on
   redis-cache (`configctl set redis-cache upstream_timeout_ms 430`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
10% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
