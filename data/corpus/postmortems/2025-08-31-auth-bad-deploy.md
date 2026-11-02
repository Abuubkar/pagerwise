---
service: auth
updated_at: 2025-09-07
incident_date: 2025-08-31
---
# Postmortem: auth regression after a deploy (2025-08-31)

## Summary

On 2025-08-31, auth broke after a deploy for 58 minutes. The cause was in postgres-primary.
The incident was sev3 and was opened by `AuthPostDeployErrors`.

## Impact

- 33% of auth requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 4,286 customers saw errors; 110 support tickets were opened.

## Timeline

All times UTC.

- **19:45** postgres-primary 3.16.1 deployed by Anthony Harris.
- **19:52** `AuthPostDeployErrors` fired; on-call acknowledged.
- **19:53** Checked the auth runbook for regression after a deploy.
- **19:55** Found the cause in postgres-primary.
- **19:57** Mitigation applied; error rate falling.
- **20:50** Recovered; incident resolved.

## Root cause

3.16.1 of postgres-primary read a column that the migration hadn't added in production yet.

Category: regression after a deploy. Component: postgres-primary.

## Contributing factors

- The regression after a deploy alert for postgres-primary had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- AUTH-2473 (platform): Add an alert on post_deploy_error_pct for postgres-primary.
- AUTH-6221 (identity): Add a regression test for: 3.16.1 of postgres-primary read a column that the migration hadn't added in production yet.
- AUTH-2471 (platform): Link the runbook from the alert.
