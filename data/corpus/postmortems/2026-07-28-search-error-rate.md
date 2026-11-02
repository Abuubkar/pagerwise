---
service: search
updated_at: 2026-08-01
incident_date: 2026-07-28
---
# Postmortem: search elevated error rate (2026-07-28)

## Summary

On 2026-07-28, search returned errors for 39 minutes. The cause was in search.
The incident was sev1 and was opened by `SearchErrorRateHigh`.

## Impact

- 17% of search requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 5,885 customers saw errors; 28 support tickets were opened.

## Timeline

All times UTC.

- **12:07** Routine traffic; nothing unusual in search.
- **12:45** `SearchErrorRateHigh` fired; on-call acknowledged.
- **12:46** Checked the search runbook for elevated error rate.
- **13:13** Found the cause in search.
- **13:16** Mitigation applied; error rate falling.
- **13:24** Recovered; incident resolved.

## Root cause

A credential for search was rotated without restarting consumers, so every call was refused.

Category: elevated error rate. Component: search.

## Contributing factors

- The elevated error rate alert for search had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- SEAR-2682 (discovery): Add an alert on error_ratio_pct for search.
- SEAR-5103 (discovery): Add a regression test for: a credential for search was rotated without restarting consumers, so every call was refused.
- SEAR-1318 (discovery): Link the runbook from the alert.
