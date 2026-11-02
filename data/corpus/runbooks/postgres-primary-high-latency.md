---
service: postgres-primary
updated_at: 2026-10-16
---
# Postgres primary: high p99 latency

Alert: `PostgresPrimaryLatencyHigh` fires when the p99 of `postgres_primary_p99_latency_ms` stays above its threshold for 5 minutes. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on its database grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Slow dependency.** Most latency is spent waiting on its database; check its own latency first.

The most common cause on postgres-primary is lock contention: it explained 6 of the
last 10 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "lock contention" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-LAT-636
   ```

4. If `postgres_primary_p99_latency_ms` stays above 2102 for 5 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on its database.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed postgres-primary --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `query_timeout_ms=380` on
   postgres-primary (`configctl set postgres-primary query_timeout_ms 380`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
20% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
