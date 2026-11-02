---
service: search
updated_at: 2026-10-04
---
# Search: high p99 latency

Alert: `SearchLatencyHigh` fires when the p99 of `search_p99_latency_ms` stays above its threshold for 5 minutes. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on inventory grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Slow dependency.** Most latency is spent waiting on inventory; check its own latency first.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.

The most common cause on search is lock contention: it explained 14 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "lock contention" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-LAT-781
   ```

4. If `search_p99_latency_ms` stays above 1593 for 10 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on inventory.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed search --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `request_timeout_ms=620` on
   search (`configctl set search request_timeout_ms 620`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 15 minutes without improvement, or at once if more than
10% of search requests are failing. Coordinate in `#discovery-oncall`.
