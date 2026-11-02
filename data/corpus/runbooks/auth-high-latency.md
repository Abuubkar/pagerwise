---
service: auth
updated_at: 2026-01-23
---
# Auth: high p99 latency

Alert: `AuthLatencyHigh` fires when the p99 of `auth_p99_latency_ms` stays above its threshold for 5 minutes. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on redis-cache grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Slow dependency.** Most latency is spent waiting on redis-cache; check its own latency first.

The most common cause on auth is garbage collection pauses: it explained 15 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "garbage collection pauses" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-LAT-992
   ```

4. If `auth_p99_latency_ms` stays above 1414 for 10 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on redis-cache.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed auth --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `worker_threads=7` on
   auth (`configctl set auth worker_threads 7`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 20 minutes without improvement, or at once if more than
25% of auth requests are failing. Coordinate in `#identity-oncall`.
