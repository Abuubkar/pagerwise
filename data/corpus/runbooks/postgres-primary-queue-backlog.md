---
service: postgres-primary
updated_at: 2026-05-30
---
# Postgres primary: queue backlog

Alert: `PostgresPrimaryConsumerLagHigh` fires when consumer lag, `postgres_primary_consumer_lag_msgs`, stays above its threshold for 10 minutes. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Slow consumers.** Each message takes longer to process than usual.
- **Too few consumers.** Consumers crashed or were scaled down.
- **Poison message.** One message fails and blocks its partition.

The most common cause on postgres-primary is slow consumers: it explained 13 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "slow consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-QUEUE-125
   ```

4. If `postgres_primary_consumer_lag_msgs` stays above 68719 for 10 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_max_poll_records=2` on
   postgres-primary (`configctl set postgres-primary consumer_max_poll_records 2`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
20% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
