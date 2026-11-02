---
service: auth
updated_at: 2026-09-10
---
# Auth: disk full

Alert: `AuthDiskFull` fires when disk usage, `auth_disk_used_pct`, rises above its threshold. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Retention not applied.** A cleanup job failed silently and old data piled up.
- **Large temporary files.** A batch job writes temp files it doesn't remove.
- **Log volume.** Debug logging left on after an investigation.

The most common cause on auth is retention not applied: it explained 18 of the
last 25 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "retention not applied" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-DISK-715
   ```

4. If `auth_disk_used_pct` stays above 83 for 8 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/auth/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `log_level=8` on
   auth (`configctl set auth log_level 8`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 15 minutes without improvement, or at once if more than
5% of auth requests are failing. Coordinate in `#identity-oncall`.
