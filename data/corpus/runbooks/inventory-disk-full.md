---
service: inventory
updated_at: 2026-10-11
---
# Inventory: disk full

Alert: `InventoryDiskFull` fires when disk usage, `inventory_disk_used_pct`, rises above its threshold. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Large temporary files.** A batch job writes temp files it doesn't remove.
- **Retention not applied.** A cleanup job failed silently and old data piled up.
- **Log volume.** Debug logging left on after an investigation.

The most common cause on inventory is large temporary files: it explained 14 of the
last 19 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "large temporary files" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-DISK-204
   ```

4. If `inventory_disk_used_pct` stays above 94 for 3 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/inventory/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `log_level=32` on
   inventory (`configctl set inventory log_level 32`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 20 minutes without improvement, or at once if more than
5% of inventory requests are failing. Coordinate in `#discovery-oncall`.
