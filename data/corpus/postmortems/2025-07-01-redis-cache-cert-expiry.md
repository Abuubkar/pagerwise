---
service: redis-cache
updated_at: 2025-07-09
incident_date: 2025-07-01
---
# Postmortem: redis-cache TLS certificate expiry (2025-07-01)

## Summary

On 2025-07-01, redis-cache rejected TLS connections for 23 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `RedisCacheCertExpiring`.

## Impact

- 42% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 39,159 customers saw errors; 112 support tickets were opened.

## Timeline

All times UTC.

- **13:26** Routine traffic; nothing unusual in redis-cache.
- **13:34** `RedisCacheCertExpiring` fired; on-call acknowledged.
- **13:40** Checked the redis-cache runbook for TLS certificate expiry.
- **13:49** Found the cause in redis-cache.
- **13:53** Mitigation applied; error rate falling.
- **13:57** Recovered; incident resolved.

## Root cause

The renewal job for redis-cache failed for 900 days because its DNS challenge record was deleted.

Category: TLS certificate expiry. Component: redis-cache.

## Contributing factors

- The TLS certificate expiry alert for redis-cache had no runbook link.
- Two teams investigated the same symptom without knowing it.

## Action items

- REDI-1646 (platform): Add an alert on cert_days_left for redis-cache.
- REDI-3849 (platform): Add a regression test for: the renewal job for redis-cache failed for 900 days because its dns challenge record was deleted.
- REDI-3970 (platform): Link the runbook from the alert.
