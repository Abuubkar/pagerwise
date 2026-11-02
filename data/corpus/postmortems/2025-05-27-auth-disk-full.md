---
service: auth
updated_at: 2025-05-29
incident_date: 2025-05-27
---
# Postmortem: auth disk full (2025-05-27)

## Summary

On 2025-05-27, auth stopped accepting writes for 157 minutes. The cause was in postgres-primary.
The incident was sev2 and was opened by `AuthDiskFull`.

## Impact

- 40% of auth requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 20,304 customers saw errors; 74 support tickets were opened.

## Timeline

All times UTC.

- **20:44** Routine traffic; nothing unusual in postgres-primary.
- **21:10** `AuthDiskFull` fired; on-call acknowledged.
- **21:25** Checked the auth runbook for disk full.
- **22:21** Found the cause in postgres-primary.
- **22:24** Mitigation applied; error rate falling.
- **23:47** Recovered; incident resolved.

## Root cause

The retention job for postgres-primary had failed for 3720 hours after a cron syntax change.

Category: disk full. Component: postgres-primary.

## Contributing factors

- The disk full alert for postgres-primary had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- AUTH-7171 (platform): Add an alert on disk_used_pct for postgres-primary.
- AUTH-7163 (identity): Add a regression test for: the retention job for postgres-primary had failed for 3720 hours after a cron syntax change.
- AUTH-8393 (platform): Link the runbook from the alert.
