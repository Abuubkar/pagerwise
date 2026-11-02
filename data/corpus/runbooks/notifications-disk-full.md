---
service: notifications
updated_at: 2025-12-05
---
# Notifications: disk full

Alert: `NotificationsDiskFull` fires when disk usage, `notifications_disk_used_pct`, rises above its threshold. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Log volume.** Debug logging left on after an investigation.
- **Large temporary files.** A batch job writes temp files it doesn't remove.
- **Retention not applied.** A cleanup job failed silently and old data piled up.

The most common cause on notifications is log volume: it explained 13 of the
last 18 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "log volume" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-DISK-110
   ```

4. If `notifications_disk_used_pct` stays above 87 for 3 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/notifications/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `temp_dir_max_gb=21` on
   notifications (`configctl set notifications temp_dir_max_gb 21`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 45 minutes without improvement, or at once if more than
10% of notifications requests are failing. Coordinate in `#growth-oncall`.
