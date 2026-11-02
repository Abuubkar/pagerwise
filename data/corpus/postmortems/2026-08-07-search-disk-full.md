---
service: search
updated_at: 2026-08-15
incident_date: 2026-08-07
---
# Postmortem: search disk full (2026-08-07)

## Summary

On 2026-08-07, search stopped accepting writes for 145 minutes. The cause was in redis-cache.
The incident was sev1 and was opened by `SearchDiskFull`.

## Impact

- 48% of search requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 23,376 customers saw errors; 81 support tickets were opened.

## Timeline

All times UTC.

- **19:13** Routine traffic; nothing unusual in redis-cache.
- **19:29** `SearchDiskFull` fired; on-call acknowledged.
- **20:22** Checked the search runbook for disk full.
- **20:56** Found the cause in redis-cache.
- **21:14** Mitigation applied; error rate falling.
- **21:54** Recovered; incident resolved.

## Root cause

The retention job for redis-cache had failed for 143 hours after a cron syntax change.

Category: disk full. Component: redis-cache.

## Contributing factors

- The disk full alert for redis-cache had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- SEAR-5495 (platform): Add an alert on disk_used_pct for redis-cache.
- SEAR-7548 (discovery): Add a regression test for: the retention job for redis-cache had failed for 143 hours after a cron syntax change.
- SEAR-1218 (discovery): Link the runbook from the alert.
