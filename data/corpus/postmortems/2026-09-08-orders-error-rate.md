---
service: orders
updated_at: 2026-09-17
incident_date: 2026-09-08
---
# Postmortem: orders elevated error rate (2026-09-08)

## Summary

On 2026-09-08, orders returned errors for 146 minutes. The cause was in inventory.
The incident was sev1 and was opened by `OrdersErrorRateHigh`.

## Impact

- 45% of orders requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 13,578 customers saw errors; 54 support tickets were opened.

## Timeline

All times UTC.

- **10:47** Routine traffic; nothing unusual in inventory.
- **11:13** `OrdersErrorRateHigh` fired; on-call acknowledged.
- **11:36** Checked the orders runbook for elevated error rate.
- **12:42** Found the cause in inventory.
- **13:01** Mitigation applied; error rate falling.
- **13:39** Recovered; incident resolved.

## Root cause

A credential for inventory was rotated without restarting consumers, so every call was refused.

Category: elevated error rate. Component: inventory.

## Contributing factors

- The elevated error rate alert for inventory had no runbook link.
- The on-call engineer had no access to the database dashboards.
- Dashboards showed averages, which hid the p99.

## Action items

- ORDE-4101 (commerce): Add an alert on error_ratio_pct for inventory.
- ORDE-5279 (commerce): Add a regression test for: a credential for inventory was rotated without restarting consumers, so every call was refused.
- ORDE-9952 (commerce): Link the runbook from the alert.
