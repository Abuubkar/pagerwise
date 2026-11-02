---
service: kafka-broker
updated_at: 2026-02-09
---
# Kafka broker: regression after a deploy

Alert: `KafkaBrokerPostDeployErrors` fires when errors in the 30 minutes after a deploy, `kafka_broker_post_deploy_error_pct`, exceed their threshold. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Config drift.** The release expects a setting that isn't present in production.
- **Code regression.** The new release breaks a path the tests don't cover.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.

The most common cause on kafka-broker is config drift: it explained 13 of the
last 17 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "config drift" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-DEPLOY-552
   ```

4. If `kafka_broker_post_deploy_error_pct` stays above 6 for 4 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback kafka-broker`; don't wait to debug.
2. Freeze deploys for kafka-broker.
3. If that doesn't help within 10 minutes, set `canary_error_threshold_pct=13` on
   kafka-broker (`configctl set kafka-broker canary_error_threshold_pct 13`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
20% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
