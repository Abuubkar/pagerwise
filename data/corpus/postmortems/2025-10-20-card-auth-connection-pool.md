---
service: card-auth
updated_at: 2025-10-27
incident_date: 2025-10-20
---
# Postmortem: card-auth connection pool exhaustion (2025-10-20)

## Summary

On 2025-10-20, card-auth ran out of database connections for 164 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `CardAuthPoolExhausted`.

## Impact

- 27% of card-auth requests failed or timed out at the peak.
- Callers affected: payments.
- 15,833 customers saw errors; 107 support tickets were opened.

## Timeline

All times UTC.

- **19:21** Routine traffic; nothing unusual in redis-cache.
- **19:29** `CardAuthPoolExhausted` fired; on-call acknowledged.
- **19:38** Checked the card-auth runbook for connection pool exhaustion.
- **21:10** Found the cause in redis-cache.
- **21:43** Mitigation applied; error rate falling.
- **22:13** Recovered; incident resolved.

## Root cause

A retry loop in redis-cache leaked one connection per failed attempt until the pool was empty.

Category: connection pool exhaustion. Component: redis-cache.

## Contributing factors

- The connection pool exhaustion alert for redis-cache had no runbook link.
- A recent reorg left the alert routed to the wrong team.
- Dashboards showed averages, which hid the p99.

## Action items

- CARD-6253 (payments): Add an alert on pool_wait_ms for redis-cache.
- CARD-1877 (payments): Add a regression test for: a retry loop in redis-cache leaked one connection per failed attempt until the pool was empty.
- CARD-9476 (platform): Link the runbook from the alert.
