---
service: notifications
updated_at: 2026-02-20
---
# Notifications: queue backlog

Alert: `NotificationsConsumerLagHigh` fires when consumer lag, `notifications_consumer_lag_msgs`, stays above its threshold for 10 minutes. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Too few consumers.** Consumers crashed or were scaled down.
- **Slow consumers.** Each message takes longer to process than usual.
- **Poison message.** One message fails and blocks its partition.

The most common cause on notifications is too few consumers: it explained 23 of the
last 27 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "too few consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-QUEUE-326
   ```

4. If `notifications_consumer_lag_msgs` stays above 35252 for 12 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_concurrency=50` on
   notifications (`configctl set notifications consumer_concurrency 50`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 20 minutes without improvement, or at once if more than
10% of notifications requests are failing. Coordinate in `#growth-oncall`.
