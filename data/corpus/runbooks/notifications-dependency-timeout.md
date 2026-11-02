---
service: notifications
updated_at: 2026-10-20
---
# Notifications: dependency timeouts

Alert: `NotificationsUpstreamTimeouts` fires when the share of calls to a dependency that time out, `notifications_upstream_timeout_pct`, stays above its threshold for 5 minutes. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- Timeouts concentrate on calls to kafka-broker.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Dependency degraded.** kafka-broker itself is slow or partially down.
- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Network path.** Packet loss between zones adds retransmits.

The most common cause on notifications is dependency degraded: it explained 6 of the
last 9 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "dependency degraded" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-DEP-129
   ```

4. If `notifications_upstream_timeout_pct` stays above 9 for 6 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check kafka-broker's own dashboard before changing anything in notifications.

## Mitigation

1. Open the circuit breaker for kafka-broker if the feature can degrade.
2. Fail over calls to the standby region for kafka-broker if one exists.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=47` on
   notifications (`configctl set notifications circuit_breaker_threshold 47`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 45 minutes without improvement, or at once if more than
25% of notifications requests are failing. Coordinate in `#growth-oncall`.
