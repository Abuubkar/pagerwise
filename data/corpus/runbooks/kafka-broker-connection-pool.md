---
service: kafka-broker
updated_at: 2026-02-22
---
# Kafka broker: connection pool exhaustion

Alert: `KafkaBrokerPoolExhausted` fires when the time requests wait for a database connection, `kafka_broker_pool_wait_ms`, stays above its threshold for 3 minutes. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Connection leak.** A code path that forgets to return connections after an error.
- **Long transactions holding connections.** A slow code path keeps connections checked out.

The most common cause on kafka-broker is pool too small for the replica count: it explained 9 of the
last 12 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-POOL-728
   ```

4. If `kafka_broker_pool_wait_ms` stays above 176 for 4 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `kafka-brokerctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/kafka-broker --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on its database.
3. If that doesn't help within 10 minutes, set `statement_timeout_ms=460` on
   kafka-broker (`configctl set kafka-broker statement_timeout_ms 460`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
10% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
