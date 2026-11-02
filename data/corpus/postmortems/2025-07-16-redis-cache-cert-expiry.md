---
service: redis-cache
updated_at: 2025-07-23
incident_date: 2025-07-16
---
# Postmortem: redis-cache TLS certificate expiry (2025-07-16)

## Summary

On 2025-07-16, redis-cache rejected TLS connections for 173 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `RedisCacheCertExpiring`.

## Impact

- 35% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 39,869 customers saw errors; 2 support tickets were opened.

## Timeline

All times UTC.

- **05:09** Routine traffic; nothing unusual in redis-cache.
- **05:15** `RedisCacheCertExpiring` fired; on-call acknowledged.
- **05:35** Checked the redis-cache runbook for TLS certificate expiry.
- **05:54** Found the cause in redis-cache.
- **06:35** Mitigation applied; error rate falling.
- **08:08** Recovered; incident resolved.

## Root cause

redis-cache pinned an intermediate certificate that the CA rotated.

Category: TLS certificate expiry. Component: redis-cache.

## Contributing factors

- The TLS certificate expiry alert for redis-cache had no runbook link.
- Two teams investigated the same symptom without knowing it.

## Action items

- REDI-4352 (platform): Add an alert on cert_days_left for redis-cache.
- REDI-4499 (platform): Add a regression test for: redis-cache pinned an intermediate certificate that the ca rotated.
- REDI-5584 (platform): Link the runbook from the alert.
