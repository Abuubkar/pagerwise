---
service: ledger
updated_at: 2026-05-25
---
# Ledger: high p99 latency

Alert: `LedgerLatencyHigh` fires when the p99 of `ledger_p99_latency_ms` stays above its threshold for 5 minutes. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on postgres-primary grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Slow dependency.** Most latency is spent waiting on postgres-primary; check its own latency first.

The most common cause on ledger is lock contention: it explained 13 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "lock contention" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-LAT-212
   ```

4. If `ledger_p99_latency_ms` stays above 688 for 6 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on postgres-primary.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed ledger --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `request_timeout_ms=180` on
   ledger (`configctl set ledger request_timeout_ms 180`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 30 minutes without improvement, or at once if more than
10% of ledger requests are failing. Coordinate in `#ledger-oncall`.
