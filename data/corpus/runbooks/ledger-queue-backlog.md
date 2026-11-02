---
service: ledger
updated_at: 2025-10-26
---
# Ledger: queue backlog

Alert: `LedgerConsumerLagHigh` fires when consumer lag, `ledger_consumer_lag_msgs`, stays above its threshold for 10 minutes. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Too few consumers.** Consumers crashed or were scaled down.
- **Slow consumers.** Each message takes longer to process than usual.
- **Poison message.** One message fails and blocks its partition.

The most common cause on ledger is too few consumers: it explained 11 of the
last 17 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "too few consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-QUEUE-882
   ```

4. If `ledger_consumer_lag_msgs` stays above 83192 for 10 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_concurrency=48` on
   ledger (`configctl set ledger consumer_concurrency 48`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 15 minutes without improvement, or at once if more than
25% of ledger requests are failing. Coordinate in `#ledger-oncall`.
