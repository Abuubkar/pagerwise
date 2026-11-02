---
service: card-auth
updated_at: 2026-02-26
incident_date: 2026-02-23
---
# Postmortem: card-auth regression after a deploy (2026-02-23)

## Summary

On 2026-02-23, card-auth broke after a deploy for 188 minutes. The cause was in card-auth.
The incident was sev1 and was opened by `CardAuthPostDeployErrors`.

## Impact

- 56% of card-auth requests failed or timed out at the peak.
- Callers affected: payments.
- 28,883 customers saw errors; 61 support tickets were opened.

## Timeline

All times UTC.

- **16:16** card-auth 5.38.18 deployed by Sophia Fuentes.
- **16:46** `CardAuthPostDeployErrors` fired; on-call acknowledged.
- **17:21** Checked the card-auth runbook for regression after a deploy.
- **17:27** Found the cause in card-auth.
- **17:44** Mitigation applied; error rate falling.
- **19:54** Recovered; incident resolved.

## Root cause

5.38.18 of card-auth read a column that the migration hadn't added in production yet.

Category: regression after a deploy. Component: card-auth.

## Contributing factors

- The regression after a deploy alert for card-auth had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- CARD-7102 (payments): Add an alert on post_deploy_error_pct for card-auth.
- CARD-1524 (payments): Add a regression test for: 5.38.18 of card-auth read a column that the migration hadn't added in production yet.
- CARD-3345 (payments): Link the runbook from the alert.
