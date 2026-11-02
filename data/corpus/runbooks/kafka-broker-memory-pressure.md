---
service: kafka-broker
updated_at: 2026-08-19
---
# Kafka broker: memory pressure and OOM kills

Alert: `KafkaBrokerMemoryPressure` fires when container memory, `kafka_broker_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Large payloads.** A few very large requests allocate far more than usual.
- **Memory leak in a recent release.** A new code path keeps references to finished requests.

The most common cause on kafka-broker is unbounded cache: it explained 16 of the
last 22 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "unbounded cache" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-MEM-725
   ```

4. If `kafka_broker_rss_pct_of_limit` stays above 82 for 8 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/kafka-broker`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `max_request_body_kb=12` on
   kafka-broker (`configctl set kafka-broker max_request_body_kb 12`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
10% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
