---
service: orders
updated_at: 2026-01-01
incident_date: 2025-12-23
---
# Postmortem: orders memory pressure and OOM kills (2025-12-23)

## Summary

On 2025-12-23, orders kept restarting for 63 minutes. The cause was in orders.
The incident was sev2 and was opened by `OrdersMemoryPressure`.

## Impact

- 47% of orders requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 15,920 customers saw errors; 0 support tickets were opened.

## Timeline

All times UTC.

- **08:39** orders 3.22.11 deployed by David Myers.
- **09:15** `OrdersMemoryPressure` fired; on-call acknowledged.
- **09:23** Checked the orders runbook for memory pressure and OOM kills.
- **09:34** Found the cause in orders.
- **09:55** Mitigation applied; error rate falling.
- **10:18** Recovered; incident resolved.

## Root cause

A cache added in 3.22.11 of orders had no eviction, growing to 3384 MB per pod.

Category: memory pressure and OOM kills. Component: orders.

## Contributing factors

- The memory pressure and OOM kills alert for orders had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- ORDE-6758 (commerce): Add an alert on rss_pct_of_limit for orders.
- ORDE-3185 (commerce): Add a regression test for: a cache added in 3.22.11 of orders had no eviction, growing to 3384 mb per pod.
- ORDE-4944 (commerce): Link the runbook from the alert.
