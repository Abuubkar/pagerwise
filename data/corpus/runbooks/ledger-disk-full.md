---
service: ledger
updated_at: 2026-06-16
---
# Ledger: disk full

Alert: `LedgerDiskFull` fires when disk usage, `ledger_disk_used_pct`, rises above its threshold. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Large temporary files.** A batch job writes temp files it doesn't remove.
- **Log volume.** Debug logging left on after an investigation.
- **Retention not applied.** A cleanup job failed silently and old data piled up.

The most common cause on ledger is large temporary files: it explained 10 of the
last 13 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "large temporary files" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-DISK-809
   ```

4. If `ledger_disk_used_pct` stays above 89 for 6 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/ledger/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `retention_days=4` on
   ledger (`configctl set ledger retention_days 4`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 15 minutes without improvement, or at once if more than
20% of ledger requests are failing. Coordinate in `#ledger-oncall`.
