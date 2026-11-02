---
service: inventory
updated_at: 2026-05-28
incident_date: 2026-05-22
---
# Postmortem: inventory elevated error rate (2026-05-22)

## Summary

On 2026-05-22, inventory returned errors for 90 minutes. The cause was in inventory.
The incident was sev1 and was opened by `InventoryErrorRateHigh`.

## Impact

- 31% of inventory requests failed or timed out at the peak.
- Callers affected: orders, search.
- 38,762 customers saw errors; 68 support tickets were opened.

## Timeline

All times UTC.

- **04:25** inventory 7.15.1 deployed by Donna Baird.
- **04:33** `InventoryErrorRateHigh` fired; on-call acknowledged.
- **04:48** Checked the inventory runbook for elevated error rate.
- **04:54** Found the cause in inventory.
- **05:17** Mitigation applied; error rate falling.
- **06:03** Recovered; incident resolved.

## Root cause

7.15.1 of inventory sent a null currency on refunds, which the validation layer rejected.

Category: elevated error rate. Component: inventory.

## Contributing factors

- The elevated error rate alert for inventory had no runbook link.
- The on-call engineer had no access to the database dashboards.
- Dashboards showed averages, which hid the p99.

## Action items

- INVE-3030 (discovery): Add an alert on error_ratio_pct for inventory.
- INVE-5810 (discovery): Add a regression test for: 7.15.1 of inventory sent a null currency on refunds, which the validation layer rejected.
- INVE-5723 (discovery): Link the runbook from the alert.
