---
service: payments
updated_at: 2025-07-28
incident_date: 2025-07-19
---
# Postmortem: payments regression after a deploy (2025-07-19)

## Summary

On 2025-07-19, payments broke after a deploy for 27 minutes. The cause was in card-auth.
The incident was sev1 and was opened by `PaymentsPostDeployErrors`.

## Impact

- 8% of payments requests failed or timed out at the peak.
- Callers affected: api-gateway, orders.
- 9,569 customers saw errors; 40 support tickets were opened.

## Timeline

All times UTC.

- **06:02** card-auth 4.11.1 deployed by Jessica Edwards.
- **06:23** `PaymentsPostDeployErrors` fired; on-call acknowledged.
- **06:23** Checked the payments runbook for regression after a deploy.
- **06:24** Found the cause in card-auth.
- **06:40** Mitigation applied; error rate falling.
- **06:50** Recovered; incident resolved.

## Root cause

4.11.1 of card-auth renamed a config key, so production fell back to a default of 2108.

Category: regression after a deploy. Component: card-auth.

## Contributing factors

- The regression after a deploy alert for card-auth had no runbook link.
- Two teams investigated the same symptom without knowing it.

## Action items

- PAYM-5895 (payments): Add an alert on post_deploy_error_pct for card-auth.
- PAYM-2727 (payments): Add a regression test for: 4.11.1 of card-auth renamed a config key, so production fell back to a default of 2108.
- PAYM-6307 (payments): Link the runbook from the alert.
