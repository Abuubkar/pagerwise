---
service: search
updated_at: 2025-12-15
---
# Search: disk full

Alert: `SearchDiskFull` fires when disk usage, `search_disk_used_pct`, rises above its threshold. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Log volume.** Debug logging left on after an investigation.
- **Retention not applied.** A cleanup job failed silently and old data piled up.
- **Large temporary files.** A batch job writes temp files it doesn't remove.

The most common cause on search is log volume: it explained 14 of the
last 15 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "log volume" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-DISK-855
   ```

4. If `search_disk_used_pct` stays above 90 for 8 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/search/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `retention_days=3` on
   search (`configctl set search retention_days 3`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 15 minutes without improvement, or at once if more than
25% of search requests are failing. Coordinate in `#discovery-oncall`.
