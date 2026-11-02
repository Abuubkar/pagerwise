---
service: notifications
updated_at: 2026-01-06
---
# Notifications: CPU saturation

Alert: `NotificationsCPUSaturated` fires when CPU utilisation, `notifications_cpu_util_pct`, stays above its threshold for 10 minutes. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Hot loop in a release.** A recent change made a common path far more expensive.
- **Traffic spike.** Legitimate load above what the current replica count serves.

The most common cause on notifications is noisy neighbour: it explained 16 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "noisy neighbour" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-CPU-815
   ```

4. If `notifications_cpu_util_pct` stays above 91 for 10 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `autoscale_max_replicas=8` on
   notifications (`configctl set notifications autoscale_max_replicas 8`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 45 minutes without improvement, or at once if more than
20% of notifications requests are failing. Coordinate in `#growth-oncall`.
