---
service: redis-cache
updated_at: 2025-06-02
incident_date: 2025-05-24
---
# Postmortem: redis-cache dependency timeouts (2025-05-24)

## Summary

On 2025-05-24, redis-cache timed out calling its dependencies for 168 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `RedisCacheUpstreamTimeouts`.

## Impact

- 4% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 14,062 customers saw errors; 91 support tickets were opened.

## Timeline

All times UTC.

- **21:29** Routine traffic; nothing unusual in redis-cache.
- **22:04** `RedisCacheUpstreamTimeouts` fired; on-call acknowledged.
- **22:15** Checked the redis-cache runbook for dependency timeouts.
- **22:28** Found the cause in redis-cache.
- **23:28** Mitigation applied; error rate falling.
- **00:52** Recovered; incident resolved.

## Root cause

redis-cache timed out because its connection to its database pinned to a single failing node.

Category: dependency timeouts. Component: redis-cache.

## Contributing factors

- The dependency timeouts alert for redis-cache had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- REDI-6547 (platform): Add an alert on upstream_timeout_pct for redis-cache.
- REDI-6999 (platform): Add a regression test for: redis-cache timed out because its connection to its database pinned to a single failing node.
- REDI-8774 (platform): Link the runbook from the alert.
