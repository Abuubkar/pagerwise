---
service: notifications
updated_at: 2026-05-25
---
# Notifications: high p99 latency

Alert: `NotificationsLatencyHigh` fires when the p99 of `notifications_p99_latency_ms` stays above its threshold for 5 minutes. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on kafka-broker grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Slow dependency.** Most latency is spent waiting on kafka-broker; check its own latency first.
- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.

The most common cause on notifications is slow dependency: it explained 11 of the
last 21 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "slow dependency" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-LAT-354
   ```

4. If `notifications_p99_latency_ms` stays above 789 for 7 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on kafka-broker.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed notifications --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `worker_threads=27` on
   notifications (`configctl set notifications worker_threads 27`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 20 minutes without improvement, or at once if more than
5% of notifications requests are failing. Coordinate in `#growth-oncall`.
