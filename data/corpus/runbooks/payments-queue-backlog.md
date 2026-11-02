---
service: payments
updated_at: 2026-07-26
---
# Payments: queue backlog

Alert: `PaymentsConsumerLagHigh` fires when consumer lag, `payments_consumer_lag_msgs`, stays above its threshold for 10 minutes. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Poison message.** One message fails and blocks its partition.
- **Slow consumers.** Each message takes longer to process than usual.
- **Too few consumers.** Consumers crashed or were scaled down.

The most common cause on payments is poison message: it explained 12 of the
last 15 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "poison message" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-QUEUE-903
   ```

4. If `payments_consumer_lag_msgs` stays above 47727 for 12 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_max_poll_records=58` on
   payments (`configctl set payments consumer_max_poll_records 58`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 15 minutes without improvement, or at once if more than
5% of payments requests are failing. Coordinate in `#payments-oncall`.
