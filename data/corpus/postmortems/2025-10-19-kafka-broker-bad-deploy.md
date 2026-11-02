---
service: kafka-broker
updated_at: 2025-10-28
incident_date: 2025-10-19
---
# Postmortem: kafka-broker regression after a deploy (2025-10-19)

## Summary

On 2025-10-19, kafka-broker broke after a deploy for 133 minutes. The cause was in kafka-broker.
The incident was sev2 and was opened by `KafkaBrokerPostDeployErrors`.

## Impact

- 33% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 10,868 customers saw errors; 69 support tickets were opened.

## Timeline

All times UTC.

- **04:21** kafka-broker 2.16.13 deployed by Mark Meza.
- **04:35** `KafkaBrokerPostDeployErrors` fired; on-call acknowledged.
- **04:49** Checked the kafka-broker runbook for regression after a deploy.
- **06:34** Found the cause in kafka-broker.
- **06:38** Mitigation applied; error rate falling.
- **06:48** Recovered; incident resolved.

## Root cause

2.16.13 of kafka-broker read a column that the migration hadn't added in production yet.

Category: regression after a deploy. Component: kafka-broker.

## Contributing factors

- The regression after a deploy alert for kafka-broker had no runbook link.
- Two teams investigated the same symptom without knowing it.

## Action items

- KAFK-6254 (platform): Add an alert on post_deploy_error_pct for kafka-broker.
- KAFK-9152 (platform): Add a regression test for: 2.16.13 of kafka-broker read a column that the migration hadn't added in production yet.
- KAFK-8631 (platform): Link the runbook from the alert.
