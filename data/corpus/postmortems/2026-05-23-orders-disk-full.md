---
service: orders
updated_at: 2026-05-28
incident_date: 2026-05-23
---
# Postmortem: orders disk full (2026-05-23)

## Summary

On 2026-05-23, orders stopped accepting writes for 95 minutes. The cause was in orders.
The incident was sev2 and was opened by `OrdersDiskFull`.

## Impact

- 28% of orders requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 26,101 customers saw errors; 99 support tickets were opened.

## Timeline

All times UTC.

- **14:36** Routine traffic; nothing unusual in orders.
- **14:42** `OrdersDiskFull` fired; on-call acknowledged.
- **15:07** Checked the orders runbook for disk full.
- **15:37** Found the cause in orders.
- **15:46** Mitigation applied; error rate falling.
- **16:17** Recovered; incident resolved.

## Root cause

Debug logging enabled during an earlier incident in orders was never turned off and filled the disk.

Category: disk full. Component: orders.

## Contributing factors

- The disk full alert for orders had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- ORDE-1659 (commerce): Add an alert on disk_used_pct for orders.
- ORDE-5354 (commerce): Add a regression test for: debug logging enabled during an earlier incident in orders was never turned off and filled the disk.
- ORDE-9884 (commerce): Link the runbook from the alert.
