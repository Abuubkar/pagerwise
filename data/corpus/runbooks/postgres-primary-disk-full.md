---
service: postgres-primary
updated_at: 2026-09-11
---
# Postgres primary: disk full

Alert: `PostgresPrimaryDiskFull` fires when disk usage, `postgres_primary_disk_used_pct`, rises above its threshold. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Log volume.** Debug logging left on after an investigation.
- **Large temporary files.** A batch job writes temp files it doesn't remove.
- **Retention not applied.** A cleanup job failed silently and old data piled up.

The most common cause on postgres-primary is log volume: it explained 26 of the
last 29 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "log volume" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-DISK-112
   ```

4. If `postgres_primary_disk_used_pct` stays above 89 for 5 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/postgres-primary/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `retention_days=5` on
   postgres-primary (`configctl set postgres-primary retention_days 5`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
25% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
