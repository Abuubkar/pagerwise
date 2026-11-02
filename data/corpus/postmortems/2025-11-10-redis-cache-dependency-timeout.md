---
service: redis-cache
updated_at: 2025-11-15
incident_date: 2025-11-10
---
# Postmortem: redis-cache dependency timeouts (2025-11-10)

## Summary

On 2025-11-10, redis-cache timed out calling its dependencies for 89 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `RedisCacheUpstreamTimeouts`.

## Impact

- 10% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 4,595 customers saw errors; 103 support tickets were opened.

## Timeline

All times UTC.

- **23:09** Routine traffic; nothing unusual in redis-cache.
- **23:43** `RedisCacheUpstreamTimeouts` fired; on-call acknowledged.
- **00:11** Checked the redis-cache runbook for dependency timeouts.
- **00:33** Found the cause in redis-cache.
- **00:34** Mitigation applied; error rate falling.
- **01:12** Recovered; incident resolved.

## Root cause

redis-cache timed out because its connection to its database pinned to a single failing node.

Category: dependency timeouts. Component: redis-cache.

## Contributing factors

- The dependency timeouts alert for redis-cache had no runbook link.
- The on-call engineer had no access to the database dashboards.
- Dashboards showed averages, which hid the p99.

## Action items

- REDI-4702 (platform): Add an alert on upstream_timeout_pct for redis-cache.
- REDI-6785 (platform): Add a regression test for: redis-cache timed out because its connection to its database pinned to a single failing node.
- REDI-8669 (platform): Link the runbook from the alert.
