---
service: card-auth
updated_at: 2026-10-22
---
# Card auth: disk full

Alert: `CardAuthDiskFull` fires when disk usage, `card_auth_disk_used_pct`, rises above its threshold. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Log volume.** Debug logging left on after an investigation.
- **Large temporary files.** A batch job writes temp files it doesn't remove.
- **Retention not applied.** A cleanup job failed silently and old data piled up.

The most common cause on card-auth is log volume: it explained 22 of the
last 30 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "log volume" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-DISK-119
   ```

4. If `card_auth_disk_used_pct` stays above 82 for 8 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/card-auth/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `retention_days=37` on
   card-auth (`configctl set card-auth retention_days 37`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 30 minutes without improvement, or at once if more than
20% of card-auth requests are failing. Coordinate in `#payments-oncall`.
