---
service: orders
updated_at: 2025-07-24
incident_date: 2025-07-15
---
# Postmortem: orders elevated error rate (2025-07-15)

## Summary

On 2025-07-15, orders returned errors for 25 minutes. The cause was in inventory.
The incident was sev1 and was opened by `OrdersErrorRateHigh`.

## Impact

- 41% of orders requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 15,696 customers saw errors; 31 support tickets were opened.

## Timeline

All times UTC.

- **18:57** inventory 4.28.19 deployed by Theresa Wells.
- **19:04** `OrdersErrorRateHigh` fired; on-call acknowledged.
- **19:11** Checked the orders runbook for elevated error rate.
- **19:16** Found the cause in inventory.
- **19:22** Mitigation applied; error rate falling.
- **19:29** Recovered; incident resolved.

## Root cause

4.28.19 of inventory sent a null currency on refunds, which the validation layer rejected.

Category: elevated error rate. Component: inventory.

## Contributing factors

- The elevated error rate alert for inventory had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- ORDE-3611 (discovery): Add an alert on error_ratio_pct for inventory.
- ORDE-6157 (discovery): Add a regression test for: 4.28.19 of inventory sent a null currency on refunds, which the validation layer rejected.
- ORDE-8461 (commerce): Link the runbook from the alert.
