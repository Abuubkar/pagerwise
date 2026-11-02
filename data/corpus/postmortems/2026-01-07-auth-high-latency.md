---
service: auth
updated_at: 2026-01-12
incident_date: 2026-01-07
---
# Postmortem: auth high p99 latency (2026-01-07)

## Summary

On 2026-01-07, auth was slow for 108 minutes. The cause was in redis-cache.
The incident was sev3 and was opened by `AuthLatencyHigh`.

## Impact

- 7% of auth requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 35,647 customers saw errors; 41 support tickets were opened.

## Timeline

All times UTC.

- **22:59** Routine traffic; nothing unusual in redis-cache.
- **23:26** `AuthLatencyHigh` fired; on-call acknowledged.
- **23:26** Checked the auth runbook for high p99 latency.
- **00:03** Found the cause in redis-cache.
- **00:22** Mitigation applied; error rate falling.
- **01:14** Recovered; incident resolved.

## Root cause

A slow query plan in redis-cache after statistics went stale made p99 climb to 1456 ms.

Category: high p99 latency. Component: redis-cache.

## Contributing factors

- The high p99 latency alert for redis-cache had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.
- Dashboards showed averages, which hid the p99.

## Action items

- AUTH-9760 (identity): Add an alert on p99_latency_ms for redis-cache.
- AUTH-7575 (identity): Add a regression test for: a slow query plan in redis-cache after statistics went stale made p99 climb to 1456 ms.
- AUTH-1983 (platform): Link the runbook from the alert.
