---
service: kafka-broker
updated_at: 2025-10-11
---
# Kafka broker: elevated error rate

Alert: `KafkaBrokerErrorRateHigh` fires when the share of 5xx responses in `kafka_broker_error_ratio_pct` stays above its threshold for 5 minutes. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Dependency errors passed through.** its database returns errors and the service doesn't degrade.
- **Bad deploy.** A recent release introduced an exception on a common path.
- **Expired credentials.** A rotated secret wasn't picked up and calls to its database are rejected.

The most common cause on kafka-broker is dependency errors passed through: it explained 9 of the
last 9 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "dependency errors passed through" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-ERR-184
   ```

4. If `kafka_broker_error_ratio_pct` stays above 2 for 5 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback kafka-broker`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `max_inflight_requests=22` on
   kafka-broker (`configctl set kafka-broker max_inflight_requests 22`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
10% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
