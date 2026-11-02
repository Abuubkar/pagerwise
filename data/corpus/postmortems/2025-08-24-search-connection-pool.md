---
service: search
updated_at: 2025-08-31
incident_date: 2025-08-24
---
# Postmortem: search connection pool exhaustion (2025-08-24)

## Summary

On 2025-08-24, search ran out of database connections for 135 minutes. The cause was in search.
The incident was sev3 and was opened by `SearchPoolExhausted`.

## Impact

- 33% of search requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 28,161 customers saw errors; 79 support tickets were opened.

## Timeline

All times UTC.

- **15:58** search 5.24.8 deployed by Ronald Martinez.
- **16:22** `SearchPoolExhausted` fired; on-call acknowledged.
- **16:22** Checked the search runbook for connection pool exhaustion.
- **17:24** Found the cause in search.
- **17:33** Mitigation applied; error rate falling.
- **18:37** Recovered; incident resolved.

## Root cause

5.24.8 of search opened a transaction before calling an external API, holding connections for up to 3502 ms.

Category: connection pool exhaustion. Component: search.

## Contributing factors

- The connection pool exhaustion alert for search had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- SEAR-3502 (discovery): Add an alert on pool_wait_ms for search.
- SEAR-7309 (discovery): Add a regression test for: 5.24.8 of search opened a transaction before calling an external api, holding connections for up to 3502 ms.
- SEAR-2397 (discovery): Link the runbook from the alert.
