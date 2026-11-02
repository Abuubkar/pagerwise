---
service: api-gateway
updated_at: 2025-10-03
---
# Api gateway: queue backlog

Alert: `ApiGatewayConsumerLagHigh` fires when consumer lag, `api_gateway_consumer_lag_msgs`, stays above its threshold for 10 minutes. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- Consumer lag grows steadily.
- Processing rate is lower than the produce rate.
- Downstream data is stale.

## Likely causes

- **Too few consumers.** Consumers crashed or were scaled down.
- **Slow consumers.** Each message takes longer to process than usual.
- **Poison message.** One message fails and blocks its partition.

The most common cause on api-gateway is too few consumers: it explained 10 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_consumer_lag_msgs` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "too few consumers" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-QUEUE-272
   ```

4. If `api_gateway_consumer_lag_msgs` stays above 65515 for 8 minutes, treat it as
   queue backlog and move to mitigation; below that it usually recovers on its own.
5. Check whether lag grows on all partitions or a few: a few points at a poison message or hot key.

## Mitigation

1. Scale consumers up to the partition count.
2. Skip and dead-letter a poison message after 3 attempts.
3. If that doesn't help within 10 minutes, set `dlq_after_attempts=9` on
   api-gateway (`configctl set api-gateway dlq_after_attempts 9`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
10% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
