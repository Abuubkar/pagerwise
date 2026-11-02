---
service: postgres-primary
updated_at: 2025-10-31
incident_date: 2025-10-29
---
# Postmortem: postgres-primary dependency timeouts (2025-10-29)

## Summary

On 2025-10-29, postgres-primary timed out calling its dependencies for 60 minutes. The cause was in postgres-primary.
The incident was sev2 and was opened by `PostgresPrimaryUpstreamTimeouts`.

## Impact

- 44% of postgres-primary requests failed or timed out at the peak.
- Callers affected: auth, inventory, ledger, orders.
- 1,737 customers saw errors; 43 support tickets were opened.

## Timeline

All times UTC.

- **02:35** postgres-primary 7.22.17 deployed by Wendy Short.
- **03:07** `PostgresPrimaryUpstreamTimeouts` fired; on-call acknowledged.
- **03:22** Checked the postgres-primary runbook for dependency timeouts.
- **03:25** Found the cause in postgres-primary.
- **03:29** Mitigation applied; error rate falling.
- **04:07** Recovered; incident resolved.

## Root cause

A config change in 7.22.17 cut the timeout to its database to below its normal p99.

Category: dependency timeouts. Component: postgres-primary.

## Contributing factors

- The dependency timeouts alert for postgres-primary had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- POST-3127 (platform): Add an alert on upstream_timeout_pct for postgres-primary.
- POST-4216 (platform): Add a regression test for: a config change in 7.22.17 cut the timeout to its database to below its normal p99.
- POST-9927 (platform): Link the runbook from the alert.
