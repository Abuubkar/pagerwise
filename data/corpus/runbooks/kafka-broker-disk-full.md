---
service: kafka-broker
updated_at: 2026-10-07
---
# Kafka broker: disk full

Alert: `KafkaBrokerDiskFull` fires when disk usage, `kafka_broker_disk_used_pct`, rises above its threshold. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Large temporary files.** A batch job writes temp files it doesn't remove.
- **Log volume.** Debug logging left on after an investigation.
- **Retention not applied.** A cleanup job failed silently and old data piled up.

The most common cause on kafka-broker is large temporary files: it explained 23 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "large temporary files" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-DISK-485
   ```

4. If `kafka_broker_disk_used_pct` stays above 88 for 8 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/kafka-broker/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `log_level=52` on
   kafka-broker (`configctl set kafka-broker log_level 52`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
25% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
