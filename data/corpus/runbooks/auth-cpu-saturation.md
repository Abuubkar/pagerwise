---
service: auth
updated_at: 2026-09-27
---
# Auth: CPU saturation

Alert: `AuthCPUSaturated` fires when CPU utilisation, `auth_cpu_util_pct`, stays above its threshold for 10 minutes. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Traffic spike.** Legitimate load above what the current replica count serves.
- **Hot loop in a release.** A recent change made a common path far more expensive.

The most common cause on auth is noisy neighbour: it explained 9 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "noisy neighbour" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-CPU-206
   ```

4. If `auth_cpu_util_pct` stays above 87 for 10 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `worker_threads=42` on
   auth (`configctl set auth worker_threads 42`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 45 minutes without improvement, or at once if more than
10% of auth requests are failing. Coordinate in `#identity-oncall`.
