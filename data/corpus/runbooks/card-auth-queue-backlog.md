---
service: card-auth
updated_at: 2026-05-11
---
# Card auth: queue backlog

Alert: `CardAuthConsumerLagHigh` fires when consumer lag, `card_auth_consumer_lag_msgs`, stays above its threshold for 10 minutes. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Too few consumers.** Consumers crashed or were scaled down.
- **Poison message.** One message fails and blocks its partition.
- **Slow consumers.** Each message takes longer to process than usual.

The most common cause on card-auth is too few consumers: it explained 8 of the
last 8 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "too few consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-QUEUE-168
   ```

4. If `card_auth_consumer_lag_msgs` stays above 84715 for 6 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_concurrency=57` on
   card-auth (`configctl set card-auth consumer_concurrency 57`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 30 minutes without improvement, or at once if more than
10% of card-auth requests are failing. Coordinate in `#payments-oncall`.
