---
service: auth
updated_at: 2026-07-09
---
# Auth: queue backlog

Alert: `AuthConsumerLagHigh` fires when consumer lag, `auth_consumer_lag_msgs`, stays above its threshold for 10 minutes. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Slow consumers.** Each message takes longer to process than usual.
- **Poison message.** One message fails and blocks its partition.
- **Too few consumers.** Consumers crashed or were scaled down.

The most common cause on auth is slow consumers: it explained 24 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "slow consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-QUEUE-890
   ```

4. If `auth_consumer_lag_msgs` stays above 26894 for 8 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_max_poll_records=36` on
   auth (`configctl set auth consumer_max_poll_records 36`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 20 minutes without improvement, or at once if more than
10% of auth requests are failing. Coordinate in `#identity-oncall`.
