---
service: redis-cache
updated_at: 2026-05-25
incident_date: 2026-05-21
---
# Postmortem: redis-cache queue backlog (2026-05-21)

## Summary

On 2026-05-21, redis-cache fell behind for 91 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `RedisCacheConsumerLagHigh`.

## Impact

- 24% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 24,918 customers saw errors; 23 support tickets were opened.

## Timeline

All times UTC.

- **15:54** redis-cache 4.24.18 deployed by Amy Miles.
- **16:04** `RedisCacheConsumerLagHigh` fired; on-call acknowledged.
- **16:06** Checked the redis-cache runbook for queue backlog.
- **16:35** Found the cause in redis-cache.
- **16:55** Mitigation applied; error rate falling.
- **17:35** Recovered; incident resolved.

## Root cause

4.24.18 of redis-cache made an external call per message, cutting throughput by two thirds.

Category: queue backlog. Component: redis-cache.

## Contributing factors

- The queue backlog alert for redis-cache had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- REDI-7488 (platform): Add an alert on consumer_lag_msgs for redis-cache.
- REDI-2882 (platform): Add a regression test for: 4.24.18 of redis-cache made an external call per message, cutting throughput by two thirds.
- REDI-9744 (platform): Link the runbook from the alert.
