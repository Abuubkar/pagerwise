---
service: search
updated_at: 2026-05-21
---
# Search: queue backlog

Alert: `SearchConsumerLagHigh` fires when consumer lag, `search_consumer_lag_msgs`, stays above its threshold for 10 minutes. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Poison message.** One message fails and blocks its partition.
- **Too few consumers.** Consumers crashed or were scaled down.
- **Slow consumers.** Each message takes longer to process than usual.

The most common cause on search is poison message: it explained 17 of the
last 18 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "poison message" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-QUEUE-942
   ```

4. If `search_consumer_lag_msgs` stays above 6141 for 7 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `dlq_after_attempts=51` on
   search (`configctl set search dlq_after_attempts 51`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 30 minutes without improvement, or at once if more than
5% of search requests are failing. Coordinate in `#discovery-oncall`.
