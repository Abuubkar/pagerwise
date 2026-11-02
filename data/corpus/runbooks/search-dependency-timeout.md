---
service: search
updated_at: 2026-05-11
---
# Search: dependency timeouts

Alert: `SearchUpstreamTimeouts` fires when the share of calls to a dependency that time out, `search_upstream_timeout_pct`, stays above its threshold for 5 minutes. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- Timeouts concentrate on calls to inventory.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Network path.** Packet loss between zones adds retransmits.
- **Dependency degraded.** inventory itself is slow or partially down.

The most common cause on search is timeout set too low: it explained 19 of the
last 27 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "timeout set too low" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-DEP-164
   ```

4. If `search_upstream_timeout_pct` stays above 1 for 12 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check inventory's own dashboard before changing anything in search.

## Mitigation

1. Open the circuit breaker for inventory if the feature can degrade.
2. Fail over calls to the standby region for inventory if one exists.
3. If that doesn't help within 10 minutes, set `upstream_timeout_ms=180` on
   search (`configctl set search upstream_timeout_ms 180`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 30 minutes without improvement, or at once if more than
20% of search requests are failing. Coordinate in `#discovery-oncall`.
