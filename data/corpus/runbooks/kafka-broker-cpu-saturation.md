---
service: kafka-broker
updated_at: 2026-07-22
---
# Kafka broker: CPU saturation

Alert: `KafkaBrokerCPUSaturated` fires when CPU utilisation, `kafka_broker_cpu_util_pct`, stays above its threshold for 10 minutes. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Traffic spike.** Legitimate load above what the current replica count serves.
- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Hot loop in a release.** A recent change made a common path far more expensive.

The most common cause on kafka-broker is traffic spike: it explained 6 of the
last 9 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "traffic spike" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-CPU-730
   ```

4. If `kafka_broker_cpu_util_pct` stays above 93 for 7 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `cache_ttl_s=17` on
   kafka-broker (`configctl set kafka-broker cache_ttl_s 17`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
10% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
