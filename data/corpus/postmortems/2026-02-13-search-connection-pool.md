---
service: search
updated_at: 2026-02-17
incident_date: 2026-02-13
---
# Postmortem: search connection pool exhaustion (2026-02-13)

## Summary

On 2026-02-13, search ran out of database connections for 116 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `SearchPoolExhausted`.

## Impact

- 47% of search requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 11,589 customers saw errors; 25 support tickets were opened.

## Timeline

All times UTC.

- **01:37** redis-cache 5.11.11 deployed by Jody Evans.
- **01:50** `SearchPoolExhausted` fired; on-call acknowledged.
- **02:13** Checked the search runbook for connection pool exhaustion.
- **02:17** Found the cause in redis-cache.
- **02:25** Mitigation applied; error rate falling.
- **03:46** Recovered; incident resolved.

## Root cause

5.11.11 of redis-cache opened a transaction before calling an external API, holding connections for up to 3577 ms.

Category: connection pool exhaustion. Component: redis-cache.

## Contributing factors

- The connection pool exhaustion alert for redis-cache had no runbook link.
- Two teams investigated the same symptom without knowing it.

## Action items

- SEAR-9117 (platform): Add an alert on pool_wait_ms for redis-cache.
- SEAR-3872 (discovery): Add a regression test for: 5.11.11 of redis-cache opened a transaction before calling an external api, holding connections for up to 3577 ms.
- SEAR-3245 (discovery): Link the runbook from the alert.
