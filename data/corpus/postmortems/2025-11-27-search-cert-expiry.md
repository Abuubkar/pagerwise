---
service: search
updated_at: 2025-12-05
incident_date: 2025-11-27
---
# Postmortem: search TLS certificate expiry (2025-11-27)

## Summary

On 2025-11-27, search rejected TLS connections for 59 minutes. The cause was in inventory.
The incident was sev2 and was opened by `SearchCertExpiring`.

## Impact

- 7% of search requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 21,712 customers saw errors; 41 support tickets were opened.

## Timeline

All times UTC.

- **13:09** Routine traffic; nothing unusual in inventory.
- **13:41** `SearchCertExpiring` fired; on-call acknowledged.
- **13:50** Checked the search runbook for TLS certificate expiry.
- **14:00** Found the cause in inventory.
- **14:15** Mitigation applied; error rate falling.
- **14:40** Recovered; incident resolved.

## Root cause

inventory pinned an intermediate certificate that the CA rotated.

Category: TLS certificate expiry. Component: inventory.

## Contributing factors

- The TLS certificate expiry alert for inventory had no runbook link.
- The on-call engineer had no access to the database dashboards.
- Dashboards showed averages, which hid the p99.

## Action items

- SEAR-4347 (discovery): Add an alert on cert_days_left for inventory.
- SEAR-1175 (discovery): Add a regression test for: inventory pinned an intermediate certificate that the ca rotated.
- SEAR-1777 (discovery): Link the runbook from the alert.
