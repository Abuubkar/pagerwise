---
service: payments
updated_at: 2025-10-13
---
# Payments: disk full

Alert: `PaymentsDiskFull` fires when disk usage, `payments_disk_used_pct`, rises above its threshold. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Retention not applied.** A cleanup job failed silently and old data piled up.
- **Log volume.** Debug logging left on after an investigation.
- **Large temporary files.** A batch job writes temp files it doesn't remove.

The most common cause on payments is retention not applied: it explained 15 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "retention not applied" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-DISK-121
   ```

4. If `payments_disk_used_pct` stays above 84 for 5 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/payments/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `log_level=53` on
   payments (`configctl set payments log_level 53`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 45 minutes without improvement, or at once if more than
10% of payments requests are failing. Coordinate in `#payments-oncall`.
