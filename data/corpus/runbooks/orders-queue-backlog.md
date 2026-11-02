---
service: orders
updated_at: 2025-09-27
---
# Orders: queue backlog

Alert: `OrdersConsumerLagHigh` fires when consumer lag, `orders_consumer_lag_msgs`, stays above its threshold for 10 minutes. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Too few consumers.** Consumers crashed or were scaled down.
- **Poison message.** One message fails and blocks its partition.
- **Slow consumers.** Each message takes longer to process than usual.

The most common cause on orders is too few consumers: it explained 27 of the
last 27 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "too few consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-QUEUE-733
   ```

4. If `orders_consumer_lag_msgs` stays above 8063 for 3 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_concurrency=31` on
   orders (`configctl set orders consumer_concurrency 31`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 45 minutes without improvement, or at once if more than
10% of orders requests are failing. Coordinate in `#commerce-oncall`.
