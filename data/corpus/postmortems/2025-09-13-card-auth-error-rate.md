---
service: card-auth
updated_at: 2025-09-18
incident_date: 2025-09-13
---
# Postmortem: card-auth elevated error rate (2025-09-13)

## Summary

On 2025-09-13, card-auth returned errors for 129 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `CardAuthErrorRateHigh`.

## Impact

- 16% of card-auth requests failed or timed out at the peak.
- Callers affected: payments.
- 12,453 customers saw errors; 65 support tickets were opened.

## Timeline

All times UTC.

- **18:12** Routine traffic; nothing unusual in redis-cache.
- **18:18** `CardAuthErrorRateHigh` fired; on-call acknowledged.
- **19:35** Checked the card-auth runbook for elevated error rate.
- **19:37** Found the cause in redis-cache.
- **20:18** Mitigation applied; error rate falling.
- **20:27** Recovered; incident resolved.

## Root cause

A credential for redis-cache was rotated without restarting consumers, so every call was refused.

Category: elevated error rate. Component: redis-cache.

## Contributing factors

- The elevated error rate alert for redis-cache had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.
- Dashboards showed averages, which hid the p99.

## Action items

- CARD-1194 (platform): Add an alert on error_ratio_pct for redis-cache.
- CARD-3659 (payments): Add a regression test for: a credential for redis-cache was rotated without restarting consumers, so every call was refused.
- CARD-6307 (platform): Link the runbook from the alert.
