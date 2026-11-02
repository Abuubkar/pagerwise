---
service: auth
updated_at: 2026-07-21
incident_date: 2026-07-16
---
# Postmortem: auth disk full (2026-07-16)

## Summary

On 2026-07-16, auth stopped accepting writes for 124 minutes. The cause was in postgres-primary.
The incident was sev2 and was opened by `AuthDiskFull`.

## Impact

- 3% of auth requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 17,847 customers saw errors; 73 support tickets were opened.

## Timeline

All times UTC.

- **10:43** Routine traffic; nothing unusual in postgres-primary.
- **11:14** `AuthDiskFull` fired; on-call acknowledged.
- **11:33** Checked the auth runbook for disk full.
- **11:48** Found the cause in postgres-primary.
- **12:07** Mitigation applied; error rate falling.
- **13:18** Recovered; incident resolved.

## Root cause

Debug logging enabled during an earlier incident in postgres-primary was never turned off and filled the disk.

Category: disk full. Component: postgres-primary.

## Contributing factors

- The disk full alert for postgres-primary had no runbook link.
- A recent reorg left the alert routed to the wrong team.
- Dashboards showed averages, which hid the p99.

## Action items

- AUTH-3749 (platform): Add an alert on disk_used_pct for postgres-primary.
- AUTH-9044 (identity): Add a regression test for: debug logging enabled during an earlier incident in postgres-primary was never turned off and filled the disk.
- AUTH-6211 (platform): Link the runbook from the alert.
