---
service: card-auth
updated_at: 2026-10-30
incident_date: 2026-10-25
---
# Postmortem: card-auth memory pressure and OOM kills (2026-10-25)

## Summary

On 2026-10-25, card-auth kept restarting for 132 minutes. The cause was in redis-cache.
The incident was sev3 and was opened by `CardAuthMemoryPressure`.

## Impact

- 41% of card-auth requests failed or timed out at the peak.
- Callers affected: payments.
- 38,440 customers saw errors; 9 support tickets were opened.

## Timeline

All times UTC.

- **10:48** redis-cache 6.38.7 deployed by Chris Curtis.
- **11:12** `CardAuthMemoryPressure` fired; on-call acknowledged.
- **11:13** Checked the card-auth runbook for memory pressure and OOM kills.
- **11:18** Found the cause in redis-cache.
- **12:11** Mitigation applied; error rate falling.
- **13:24** Recovered; incident resolved.

## Root cause

redis-cache buffered whole export files in memory after a change in 6.38.7.

Category: memory pressure and OOM kills. Component: redis-cache.

## Contributing factors

- The memory pressure and OOM kills alert for redis-cache had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- CARD-1539 (platform): Add an alert on rss_pct_of_limit for redis-cache.
- CARD-2833 (platform): Add a regression test for: redis-cache buffered whole export files in memory after a change in 6.38.7.
- CARD-3651 (payments): Link the runbook from the alert.
