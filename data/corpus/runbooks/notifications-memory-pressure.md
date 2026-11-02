---
service: notifications
updated_at: 2025-10-30
---
# Notifications: memory pressure and OOM kills

Alert: `NotificationsMemoryPressure` fires when container memory, `notifications_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Large payloads.** A few very large requests allocate far more than usual.

The most common cause on notifications is memory leak in a recent release: it explained 19 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "memory leak in a recent release" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-MEM-101
   ```

4. If `notifications_rss_pct_of_limit` stays above 97 for 3 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/notifications`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `cache_max_entries=16` on
   notifications (`configctl set notifications cache_max_entries 16`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 20 minutes without improvement, or at once if more than
20% of notifications requests are failing. Coordinate in `#growth-oncall`.
