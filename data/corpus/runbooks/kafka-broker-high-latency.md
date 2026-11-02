---
service: kafka-broker
updated_at: 2026-04-27
---
# Kafka broker: high p99 latency

Alert: `KafkaBrokerLatencyHigh` fires when the p99 of `kafka_broker_p99_latency_ms` stays above its threshold for 5 minutes. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on its database grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Slow dependency.** Most latency is spent waiting on its database; check its own latency first.

The most common cause on kafka-broker is garbage collection pauses: it explained 12 of the
last 21 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "garbage collection pauses" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-LAT-509
   ```

4. If `kafka_broker_p99_latency_ms` stays above 2259 for 12 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on its database.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed kafka-broker --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `request_timeout_ms=60` on
   kafka-broker (`configctl set kafka-broker request_timeout_ms 60`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
5% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
