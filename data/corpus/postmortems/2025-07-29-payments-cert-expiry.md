---
service: payments
updated_at: 2025-08-07
incident_date: 2025-07-29
---
# Postmortem: payments TLS certificate expiry (2025-07-29)

## Summary

On 2025-07-29, payments rejected TLS connections for 167 minutes. The cause was in payments.
The incident was sev2 and was opened by `PaymentsCertExpiring`.

## Impact

- 52% of payments requests failed or timed out at the peak.
- Callers affected: api-gateway, orders.
- 10,085 customers saw errors; 26 support tickets were opened.

## Timeline

All times UTC.

- **12:24** Routine traffic; nothing unusual in payments.
- **12:40** `PaymentsCertExpiring` fired; on-call acknowledged.
- **13:05** Checked the payments runbook for TLS certificate expiry.
- **13:16** Found the cause in payments.
- **13:39** Mitigation applied; error rate falling.
- **15:27** Recovered; incident resolved.

## Root cause

payments pinned an intermediate certificate that the CA rotated.

Category: TLS certificate expiry. Component: payments.

## Contributing factors

- The TLS certificate expiry alert for payments had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- PAYM-2481 (payments): Add an alert on cert_days_left for payments.
- PAYM-4233 (payments): Add a regression test for: payments pinned an intermediate certificate that the ca rotated.
- PAYM-4491 (payments): Link the runbook from the alert.
