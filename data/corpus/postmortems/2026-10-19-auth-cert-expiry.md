---
service: auth
updated_at: 2026-10-23
incident_date: 2026-10-19
---
# Postmortem: auth TLS certificate expiry (2026-10-19)

## Summary

On 2026-10-19, auth rejected TLS connections for 171 minutes. The cause was in redis-cache.
The incident was sev3 and was opened by `AuthCertExpiring`.

## Impact

- 8% of auth requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 4,252 customers saw errors; 81 support tickets were opened.

## Timeline

All times UTC.

- **17:54** Routine traffic; nothing unusual in redis-cache.
- **18:14** `AuthCertExpiring` fired; on-call acknowledged.
- **18:17** Checked the auth runbook for TLS certificate expiry.
- **18:48** Found the cause in redis-cache.
- **18:54** Mitigation applied; error rate falling.
- **21:05** Recovered; incident resolved.

## Root cause

redis-cache pinned an intermediate certificate that the CA rotated.

Category: TLS certificate expiry. Component: redis-cache.

## Contributing factors

- The TLS certificate expiry alert for redis-cache had no runbook link.
- The on-call engineer had no access to the database dashboards.
- Dashboards showed averages, which hid the p99.

## Action items

- AUTH-7585 (platform): Add an alert on cert_days_left for redis-cache.
- AUTH-1188 (identity): Add a regression test for: redis-cache pinned an intermediate certificate that the ca rotated.
- AUTH-6739 (platform): Link the runbook from the alert.
