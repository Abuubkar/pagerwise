---
service: inventory
updated_at: 2026-05-06
incident_date: 2026-04-27
---
# Postmortem: inventory regression after a deploy (2026-04-27)

## Summary

On 2026-04-27, inventory broke after a deploy for 111 minutes. The cause was in postgres-primary.
The incident was sev1 and was opened by `InventoryPostDeployErrors`.

## Impact

- 45% of inventory requests failed or timed out at the peak.
- Callers affected: orders, search.
- 4,554 customers saw errors; 67 support tickets were opened.

## Timeline

All times UTC.

- **18:22** postgres-primary 9.39.13 deployed by Pamela Berry.
- **18:49** `InventoryPostDeployErrors` fired; on-call acknowledged.
- **18:54** Checked the inventory runbook for regression after a deploy.
- **19:34** Found the cause in postgres-primary.
- **19:48** Mitigation applied; error rate falling.
- **20:40** Recovered; incident resolved.

## Root cause

9.39.13 of postgres-primary renamed a config key, so production fell back to a default of 4250.

Category: regression after a deploy. Component: postgres-primary.

## Contributing factors

- The regression after a deploy alert for postgres-primary had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- INVE-7709 (platform): Add an alert on post_deploy_error_pct for postgres-primary.
- INVE-9206 (platform): Add a regression test for: 9.39.13 of postgres-primary renamed a config key, so production fell back to a default of 4250.
- INVE-3526 (discovery): Link the runbook from the alert.
