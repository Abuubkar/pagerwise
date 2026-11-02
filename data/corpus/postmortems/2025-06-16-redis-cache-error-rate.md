---
service: redis-cache
updated_at: 2025-06-24
incident_date: 2025-06-16
---
# Postmortem: redis-cache elevated error rate (2025-06-16)

## Summary

On 2025-06-16, redis-cache returned errors for 89 minutes. The cause was in redis-cache.
The incident was sev1 and was opened by `RedisCacheErrorRateHigh`.

## Impact

- 33% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 37,272 customers saw errors; 66 support tickets were opened.

## Timeline

All times UTC.

- **20:54** Routine traffic; nothing unusual in redis-cache.
- **21:00** `RedisCacheErrorRateHigh` fired; on-call acknowledged.
- **21:04** Checked the redis-cache runbook for elevated error rate.
- **21:23** Found the cause in redis-cache.
- **21:40** Mitigation applied; error rate falling.
- **22:29** Recovered; incident resolved.

## Root cause

A credential for redis-cache was rotated without restarting consumers, so every call was refused.

Category: elevated error rate. Component: redis-cache.

## Contributing factors

- The elevated error rate alert for redis-cache had no runbook link.
- Two teams investigated the same symptom without knowing it.

## Action items

- REDI-7898 (platform): Add an alert on error_ratio_pct for redis-cache.
- REDI-8314 (platform): Add a regression test for: a credential for redis-cache was rotated without restarting consumers, so every call was refused.
- REDI-1231 (platform): Link the runbook from the alert.
