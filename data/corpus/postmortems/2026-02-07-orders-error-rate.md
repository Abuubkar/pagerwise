---
service: orders
updated_at: 2026-02-11
incident_date: 2026-02-07
---
# Postmortem: orders elevated error rate (2026-02-07)

## Summary

On 2026-02-07, orders returned errors for 76 minutes. The cause was in inventory.
The incident was sev2 and was opened by `OrdersErrorRateHigh`.

## Impact

- 51% of orders requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 776 customers saw errors; 49 support tickets were opened.

## Timeline

All times UTC.

- **13:49** inventory 2.26.7 deployed by Benjamin Davis.
- **14:20** `OrdersErrorRateHigh` fired; on-call acknowledged.
- **14:22** Checked the orders runbook for elevated error rate.
- **15:14** Found the cause in inventory.
- **15:18** Mitigation applied; error rate falling.
- **15:36** Recovered; incident resolved.

## Root cause

2.26.7 of inventory sent a null currency on refunds, which the validation layer rejected.

Category: elevated error rate. Component: inventory.

## Contributing factors

- The elevated error rate alert for inventory had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- ORDE-1624 (commerce): Add an alert on error_ratio_pct for inventory.
- ORDE-9902 (discovery): Add a regression test for: 2.26.7 of inventory sent a null currency on refunds, which the validation layer rejected.
- ORDE-3635 (discovery): Link the runbook from the alert.
