---
service: inventory
updated_at: 2025-06-07
incident_date: 2025-06-04
---
# Postmortem: inventory queue backlog (2025-06-04)

## Summary

On 2025-06-04, inventory fell behind for 66 minutes. The cause was in postgres-primary.
The incident was sev1 and was opened by `InventoryConsumerLagHigh`.

## Impact

- 15% of inventory requests failed or timed out at the peak.
- Callers affected: orders, search.
- 8,032 customers saw errors; 16 support tickets were opened.

## Timeline

All times UTC.

- **22:04** postgres-primary 7.35.3 deployed by Scott Roberts.
- **22:09** `InventoryConsumerLagHigh` fired; on-call acknowledged.
- **22:09** Checked the inventory runbook for queue backlog.
- **22:10** Found the cause in postgres-primary.
- **22:28** Mitigation applied; error rate falling.
- **23:15** Recovered; incident resolved.

## Root cause

7.35.3 of postgres-primary made an external call per message, cutting throughput by two thirds.

Category: queue backlog. Component: postgres-primary.

## Contributing factors

- The queue backlog alert for postgres-primary had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- INVE-5512 (discovery): Add an alert on consumer_lag_msgs for postgres-primary.
- INVE-8385 (discovery): Add a regression test for: 7.35.3 of postgres-primary made an external call per message, cutting throughput by two thirds.
- INVE-1821 (platform): Link the runbook from the alert.
