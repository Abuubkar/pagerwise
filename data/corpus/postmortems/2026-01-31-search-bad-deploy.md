---
service: search
updated_at: 2026-02-04
incident_date: 2026-01-31
---
# Postmortem: search regression after a deploy (2026-01-31)

## Summary

On 2026-01-31, search broke after a deploy for 88 minutes. The cause was in inventory.
The incident was sev2 and was opened by `SearchPostDeployErrors`.

## Impact

- 40% of search requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 28,938 customers saw errors; 75 support tickets were opened.

## Timeline

All times UTC.

- **07:37** inventory 6.13.12 deployed by James Barnett.
- **08:10** `SearchPostDeployErrors` fired; on-call acknowledged.
- **08:36** Checked the search runbook for regression after a deploy.
- **08:39** Found the cause in inventory.
- **09:10** Mitigation applied; error rate falling.
- **09:38** Recovered; incident resolved.

## Root cause

6.13.12 of inventory read a column that the migration hadn't added in production yet.

Category: regression after a deploy. Component: inventory.

## Contributing factors

- The regression after a deploy alert for inventory had no runbook link.
- A recent reorg left the alert routed to the wrong team.

## Action items

- SEAR-7621 (discovery): Add an alert on post_deploy_error_pct for inventory.
- SEAR-3056 (discovery): Add a regression test for: 6.13.12 of inventory read a column that the migration hadn't added in production yet.
- SEAR-9405 (discovery): Link the runbook from the alert.
