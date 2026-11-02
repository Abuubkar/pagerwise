---
service: kafka-broker
updated_at: 2026-04-22
---
# Kafka broker: dependency timeouts

Alert: `KafkaBrokerUpstreamTimeouts` fires when the share of calls to a dependency that time out, `kafka_broker_upstream_timeout_pct`, stays above its threshold for 5 minutes. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- Timeouts concentrate on calls to its database.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Dependency degraded.** its database itself is slow or partially down.
- **Network path.** Packet loss between zones adds retransmits.
- **Timeout set too low.** A recent config change shortened the timeout below normal latency.

The most common cause on kafka-broker is dependency degraded: it explained 14 of the
last 16 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "dependency degraded" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-DEP-358
   ```

4. If `kafka_broker_upstream_timeout_pct` stays above 9 for 4 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check its database's own dashboard before changing anything in kafka-broker.

## Mitigation

1. Open the circuit breaker for its database if the feature can degrade.
2. Fail over calls to the standby region for its database if one exists.
3. If that doesn't help within 10 minutes, set `retry_max_attempts=42` on
   kafka-broker (`configctl set kafka-broker retry_max_attempts 42`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
20% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
