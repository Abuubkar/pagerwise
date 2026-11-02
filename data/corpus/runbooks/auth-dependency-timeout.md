---
service: auth
updated_at: 2026-08-30
---
# Auth: dependency timeouts

Alert: `AuthUpstreamTimeouts` fires when the share of calls to a dependency that time out, `auth_upstream_timeout_pct`, stays above its threshold for 5 minutes. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- Timeouts concentrate on calls to redis-cache.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Dependency degraded.** redis-cache itself is slow or partially down.
- **Network path.** Packet loss between zones adds retransmits.
- **Timeout set too low.** A recent config change shortened the timeout below normal latency.

The most common cause on auth is dependency degraded: it explained 13 of the
last 23 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "dependency degraded" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-DEP-252
   ```

4. If `auth_upstream_timeout_pct` stays above 4 for 10 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check redis-cache's own dashboard before changing anything in auth.

## Mitigation

1. Open the circuit breaker for redis-cache if the feature can degrade.
2. Fail over calls to the standby region for redis-cache if one exists.
3. If that doesn't help within 10 minutes, set `retry_max_attempts=18` on
   auth (`configctl set auth retry_max_attempts 18`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 45 minutes without improvement, or at once if more than
25% of auth requests are failing. Coordinate in `#identity-oncall`.
