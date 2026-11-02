---
service: card-auth
updated_at: 2025-12-22
---
# Card auth: high p99 latency

Alert: `CardAuthLatencyHigh` fires when the p99 of `card_auth_p99_latency_ms` stays above its threshold for 5 minutes. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on redis-cache grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Slow dependency.** Most latency is spent waiting on redis-cache; check its own latency first.

The most common cause on card-auth is garbage collection pauses: it explained 18 of the
last 18 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "garbage collection pauses" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-LAT-675
   ```

4. If `card_auth_p99_latency_ms` stays above 1639 for 12 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on redis-cache.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed card-auth --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `request_timeout_ms=500` on
   card-auth (`configctl set card-auth request_timeout_ms 500`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 20 minutes without improvement, or at once if more than
20% of card-auth requests are failing. Coordinate in `#payments-oncall`.
