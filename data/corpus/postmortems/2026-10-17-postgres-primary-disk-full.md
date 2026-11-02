---
service: postgres-primary
updated_at: 2026-10-25
incident_date: 2026-10-17
---
# Postmortem: postgres-primary disk full (2026-10-17)

## Summary

On 2026-10-17, postgres-primary stopped accepting writes for 94 minutes. The cause was in postgres-primary.
The incident was sev1 and was opened by `PostgresPrimaryDiskFull`.

## Impact

- 29% of postgres-primary requests failed or timed out at the peak.
- Callers affected: auth, inventory, ledger, orders.
- 34,068 customers saw errors; 98 support tickets were opened.

## Timeline

All times UTC.

- **08:55** Routine traffic; nothing unusual in postgres-primary.
- **09:01** `PostgresPrimaryDiskFull` fired; on-call acknowledged.
- **09:37** Checked the postgres-primary runbook for disk full.
- **10:01** Found the cause in postgres-primary.
- **10:05** Mitigation applied; error rate falling.
- **10:35** Recovered; incident resolved.

## Root cause

The retention job for postgres-primary had failed for 408 hours after a cron syntax change.

Category: disk full. Component: postgres-primary.

## Contributing factors

- The disk full alert for postgres-primary had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- POST-8683 (platform): Add an alert on disk_used_pct for postgres-primary.
- POST-9812 (platform): Add a regression test for: the retention job for postgres-primary had failed for 408 hours after a cron syntax change.
- POST-2489 (platform): Link the runbook from the alert.
