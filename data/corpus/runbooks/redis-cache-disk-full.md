---
service: redis-cache
updated_at: 2025-11-30
---
# Redis cache: disk full

Alert: `RedisCacheDiskFull` fires when disk usage, `redis_cache_disk_used_pct`, rises above its threshold. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Log volume.** Debug logging left on after an investigation.
- **Retention not applied.** A cleanup job failed silently and old data piled up.
- **Large temporary files.** A batch job writes temp files it doesn't remove.

The most common cause on redis-cache is log volume: it explained 14 of the
last 20 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "log volume" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-DISK-856
   ```

4. If `redis_cache_disk_used_pct` stays above 89 for 7 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/redis-cache/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `temp_dir_max_gb=64` on
   redis-cache (`configctl set redis-cache temp_dir_max_gb 64`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
25% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
