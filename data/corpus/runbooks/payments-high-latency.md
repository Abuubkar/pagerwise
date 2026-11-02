---
service: payments
updated_at: 2025-10-22
---
# Payments: high p99 latency

Alert: `PaymentsLatencyHigh` fires when the p99 of `payments_p99_latency_ms` stays above its threshold for 5 minutes. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on card-auth grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Slow dependency.** Most latency is spent waiting on card-auth; check its own latency first.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.

The most common cause on payments is slow dependency: it explained 10 of the
last 19 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "slow dependency" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-LAT-857
   ```

4. If `payments_p99_latency_ms` stays above 2275 for 10 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on card-auth.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed payments --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `request_timeout_ms=140` on
   payments (`configctl set payments request_timeout_ms 140`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 15 minutes without improvement, or at once if more than
20% of payments requests are failing. Coordinate in `#payments-oncall`.
