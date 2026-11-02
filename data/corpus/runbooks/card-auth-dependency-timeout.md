---
service: card-auth
updated_at: 2026-06-14
---
# Card auth: dependency timeouts

Alert: `CardAuthUpstreamTimeouts` fires when the share of calls to a dependency that time out, `card_auth_upstream_timeout_pct`, stays above its threshold for 5 minutes. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- Timeouts concentrate on calls to redis-cache.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Network path.** Packet loss between zones adds retransmits.
- **Dependency degraded.** redis-cache itself is slow or partially down.

The most common cause on card-auth is timeout set too low: it explained 9 of the
last 16 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "timeout set too low" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-DEP-215
   ```

4. If `card_auth_upstream_timeout_pct` stays above 9 for 4 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check redis-cache's own dashboard before changing anything in card-auth.

## Mitigation

1. Open the circuit breaker for redis-cache if the feature can degrade.
2. Fail over calls to the standby region for redis-cache if one exists.
3. If that doesn't help within 10 minutes, set `upstream_timeout_ms=640` on
   card-auth (`configctl set card-auth upstream_timeout_ms 640`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 20 minutes without improvement, or at once if more than
20% of card-auth requests are failing. Coordinate in `#payments-oncall`.
