---
service: redis-cache
updated_at: 2026-01-10
---
# Redis cache: queue backlog

Alert: `RedisCacheConsumerLagHigh` fires when consumer lag, `redis_cache_consumer_lag_msgs`, stays above its threshold for 10 minutes. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Too few consumers.** Consumers crashed or were scaled down.
- **Poison message.** One message fails and blocks its partition.
- **Slow consumers.** Each message takes longer to process than usual.

The most common cause on redis-cache is too few consumers: it explained 14 of the
last 16 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "too few consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-QUEUE-485
   ```

4. If `redis_cache_consumer_lag_msgs` stays above 73703 for 6 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_concurrency=23` on
   redis-cache (`configctl set redis-cache consumer_concurrency 23`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
10% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
