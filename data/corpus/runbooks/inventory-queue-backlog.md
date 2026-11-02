---
service: inventory
updated_at: 2026-01-31
---
# Inventory: queue backlog

Alert: `InventoryConsumerLagHigh` fires when consumer lag, `inventory_consumer_lag_msgs`, stays above its threshold for 10 minutes. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Poison message.** One message fails and blocks its partition.
- **Slow consumers.** Each message takes longer to process than usual.
- **Too few consumers.** Consumers crashed or were scaled down.

The most common cause on inventory is poison message: it explained 16 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "poison message" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-QUEUE-203
   ```

4. If `inventory_consumer_lag_msgs` stays above 13293 for 10 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `consumer_concurrency=44` on
   inventory (`configctl set inventory consumer_concurrency 44`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 20 minutes without improvement, or at once if more than
25% of inventory requests are failing. Coordinate in `#discovery-oncall`.
