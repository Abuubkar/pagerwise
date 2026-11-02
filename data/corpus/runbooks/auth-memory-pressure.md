---
service: auth
updated_at: 2025-09-27
---
# Auth: memory pressure and OOM kills

Alert: `AuthMemoryPressure` fires when container memory, `auth_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Large payloads.** A few very large requests allocate far more than usual.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.

The most common cause on auth is memory leak in a recent release: it explained 22 of the
last 22 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "memory leak in a recent release" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-MEM-724
   ```

4. If `auth_rss_pct_of_limit` stays above 97 for 8 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/auth`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `gc_target_pct=22` on
   auth (`configctl set auth gc_target_pct 22`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 45 minutes without improvement, or at once if more than
25% of auth requests are failing. Coordinate in `#identity-oncall`.
