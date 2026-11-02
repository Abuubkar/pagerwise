---
service: orders
updated_at: 2026-07-10
---
# Orders: disk full

Alert: `OrdersDiskFull` fires when disk usage, `orders_disk_used_pct`, rises above its threshold. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Retention not applied.** A cleanup job failed silently and old data piled up.
- **Log volume.** Debug logging left on after an investigation.
- **Large temporary files.** A batch job writes temp files it doesn't remove.

The most common cause on orders is retention not applied: it explained 24 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "retention not applied" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-DISK-188
   ```

4. If `orders_disk_used_pct` stays above 81 for 10 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/orders/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `temp_dir_max_gb=41` on
   orders (`configctl set orders temp_dir_max_gb 41`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 45 minutes without improvement, or at once if more than
10% of orders requests are failing. Coordinate in `#commerce-oncall`.
