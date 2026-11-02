---
service: kafka-broker
updated_at: 2026-10-04
---
# Kafka broker: queue backlog

Alert: `KafkaBrokerConsumerLagHigh` fires when consumer lag, `kafka_broker_consumer_lag_msgs`, stays above its threshold for 10 minutes. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Poison message.** One message fails and blocks its partition.
- **Slow consumers.** Each message takes longer to process than usual.
- **Too few consumers.** Consumers crashed or were scaled down.

The most common cause on kafka-broker is poison message: it explained 5 of the
last 8 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "poison message" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-QUEUE-600
   ```

4. If `kafka_broker_consumer_lag_msgs` stays above 11262 for 5 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_max_poll_records=41` on
   kafka-broker (`configctl set kafka-broker consumer_max_poll_records 41`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
20% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
