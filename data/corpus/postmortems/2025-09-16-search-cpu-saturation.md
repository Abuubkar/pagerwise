---
service: search
updated_at: 2025-09-19
incident_date: 2025-09-16
---
# Postmortem: search CPU saturation (2025-09-16)

## Summary

On 2025-09-16, search was saturated for 189 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `SearchCPUSaturated`.

## Impact

- 53% of search requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 32,871 customers saw errors; 97 support tickets were opened.

## Timeline

All times UTC.

- **12:50** redis-cache 3.19.0 deployed by Joel Jackson.
- **13:01** `SearchCPUSaturated` fired; on-call acknowledged.
- **13:46** Checked the search runbook for CPU saturation.
- **13:49** Found the cause in redis-cache.
- **14:00** Mitigation applied; error rate falling.
- **16:10** Recovered; incident resolved.

## Root cause

A regex added in 3.19.0 of redis-cache backtracked on long inputs, pinning CPU at 3206%.

Category: CPU saturation. Component: redis-cache.

## Contributing factors

- The CPU saturation alert for redis-cache had no runbook link.
- A recent reorg left the alert routed to the wrong team.

## Action items

- SEAR-2079 (platform): Add an alert on cpu_util_pct for redis-cache.
- SEAR-2440 (discovery): Add a regression test for: a regex added in 3.19.0 of redis-cache backtracked on long inputs, pinning cpu at 3206%.
- SEAR-5727 (discovery): Link the runbook from the alert.
