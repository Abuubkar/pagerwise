---
service: notifications
updated_at: 2026-03-06
---
# Notifications: elevated error rate

Alert: `NotificationsErrorRateHigh` fires when the share of 5xx responses in `notifications_error_ratio_pct` stays above its threshold for 5 minutes. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Expired credentials.** A rotated secret wasn't picked up and calls to kafka-broker are rejected.
- **Dependency errors passed through.** kafka-broker returns errors and the service doesn't degrade.
- **Bad deploy.** A recent release introduced an exception on a common path.

The most common cause on notifications is expired credentials: it explained 20 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "expired credentials" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-ERR-701
   ```

4. If `notifications_error_ratio_pct` stays above 8 for 12 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback notifications`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=2` on
   notifications (`configctl set notifications circuit_breaker_threshold 2`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 20 minutes without improvement, or at once if more than
5% of notifications requests are failing. Coordinate in `#growth-oncall`.
