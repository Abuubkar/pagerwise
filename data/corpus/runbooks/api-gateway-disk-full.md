---
service: api-gateway
updated_at: 2026-02-20
---
# Api gateway: disk full

Alert: `ApiGatewayDiskFull` fires when disk usage, `api_gateway_disk_used_pct`, rises above its threshold. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- Writes fail with 'no space left on device'.
- Log volume grew sharply in the last day.
- Compaction or cleanup jobs are behind.

## Likely causes

- **Log volume.** Debug logging left on after an investigation.
- **Retention not applied.** A cleanup job failed silently and old data piled up.
- **Large temporary files.** A batch job writes temp files it doesn't remove.

The most common cause on api-gateway is log volume: it explained 18 of the
last 24 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_disk_used_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "log volume" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-DISK-815
   ```

4. If `api_gateway_disk_used_pct` stays above 87 for 5 minutes, treat it as
   disk full and move to mitigation; below that it usually recovers on its own.
5. Find the largest directories with `du -sh /var/lib/api-gateway/* | sort -h | tail`.

## Mitigation

1. Delete rotated logs older than 2 days.
2. Expand the volume by 50% if cleanup isn't enough.
3. If that doesn't help within 10 minutes, set `log_level=7` on
   api-gateway (`configctl set api-gateway log_level 7`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
20% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
