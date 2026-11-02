---
service: kafka-broker
updated_at: 2026-05-21
incident_date: 2026-05-13
---
# Postmortem: kafka-broker regression after a deploy (2026-05-13)

## Summary

On 2026-05-13, kafka-broker broke after a deploy for 152 minutes. The cause was in kafka-broker.
The incident was sev2 and was opened by `KafkaBrokerPostDeployErrors`.

## Impact

- 57% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 39,882 customers saw errors; 14 support tickets were opened.

## Timeline

All times UTC.

- **21:31** kafka-broker 3.26.3 deployed by John Williams.
- **21:45** `KafkaBrokerPostDeployErrors` fired; on-call acknowledged.
- **22:15** Checked the kafka-broker runbook for regression after a deploy.
- **23:26** Found the cause in kafka-broker.
- **23:52** Mitigation applied; error rate falling.
- **00:17** Recovered; incident resolved.

## Root cause

3.26.3 of kafka-broker renamed a config key, so production fell back to a default of 47.

Category: regression after a deploy. Component: kafka-broker.

## Contributing factors

- The regression after a deploy alert for kafka-broker had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.
- Dashboards showed averages, which hid the p99.

## Action items

- KAFK-8502 (platform): Add an alert on post_deploy_error_pct for kafka-broker.
- KAFK-6777 (platform): Add a regression test for: 3.26.3 of kafka-broker renamed a config key, so production fell back to a default of 47.
- KAFK-6782 (platform): Link the runbook from the alert.
