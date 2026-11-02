---
service: inventory
updated_at: 2026-10-09
incident_date: 2026-10-07
---
# Postmortem: inventory TLS certificate expiry (2026-10-07)

## Summary

On 2026-10-07, inventory rejected TLS connections for 115 minutes. The cause was in inventory.
The incident was sev2 and was opened by `InventoryCertExpiring`.

## Impact

- 11% of inventory requests failed or timed out at the peak.
- Callers affected: orders, search.
- 27,158 customers saw errors; 25 support tickets were opened.

## Timeline

All times UTC.

- **16:04** Routine traffic; nothing unusual in inventory.
- **16:15** `InventoryCertExpiring` fired; on-call acknowledged.
- **16:22** Checked the inventory runbook for TLS certificate expiry.
- **16:35** Found the cause in inventory.
- **16:38** Mitigation applied; error rate falling.
- **18:10** Recovered; incident resolved.

## Root cause

The renewal job for inventory failed for 4366 days because its DNS challenge record was deleted.

Category: TLS certificate expiry. Component: inventory.

## Contributing factors

- The TLS certificate expiry alert for inventory had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- INVE-9332 (discovery): Add an alert on cert_days_left for inventory.
- INVE-2044 (discovery): Add a regression test for: the renewal job for inventory failed for 4366 days because its dns challenge record was deleted.
- INVE-1794 (discovery): Link the runbook from the alert.
