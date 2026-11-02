---
service: redis-cache
updated_at: 2026-09-03
incident_date: 2026-08-28
---
# Postmortem: redis-cache connection pool exhaustion (2026-08-28)

## Summary

On 2026-08-28, redis-cache ran out of database connections for 14 minutes. The cause was in redis-cache.
The incident was sev3 and was opened by `RedisCachePoolExhausted`.

## Impact

- 55% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 6,535 customers saw errors; 75 support tickets were opened.

## Timeline

All times UTC.

- **21:31** Routine traffic; nothing unusual in redis-cache.
- **21:36** `RedisCachePoolExhausted` fired; on-call acknowledged.
- **21:36** Checked the redis-cache runbook for connection pool exhaustion.
- **21:40** Found the cause in redis-cache.
- **21:44** Mitigation applied; error rate falling.
- **21:50** Recovered; incident resolved.

## Root cause

A retry loop in redis-cache leaked one connection per failed attempt until the pool was empty.

Category: connection pool exhaustion. Component: redis-cache.

## Contributing factors

- The connection pool exhaustion alert for redis-cache had no runbook link.
- Two teams investigated the same symptom without knowing it.

## Action items

- REDI-4221 (platform): Add an alert on pool_wait_ms for redis-cache.
- REDI-9156 (platform): Add a regression test for: a retry loop in redis-cache leaked one connection per failed attempt until the pool was empty.
- REDI-9707 (platform): Link the runbook from the alert.
