---
service: kafka-broker
updated_at: 2026-05-14
incident_date: 2026-05-06
---
# Postmortem: kafka-broker dependency timeouts (2026-05-06)

## Summary

On 2026-05-06, kafka-broker timed out calling its dependencies for 57 minutes. The cause was in kafka-broker.
The incident was sev1 and was opened by `KafkaBrokerUpstreamTimeouts`.

## Impact

- 44% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 30,395 customers saw errors; 31 support tickets were opened.

## Timeline

All times UTC.

- **11:58** kafka-broker 8.40.20 deployed by Anthony Tate.
- **12:25** `KafkaBrokerUpstreamTimeouts` fired; on-call acknowledged.
- **12:26** Checked the kafka-broker runbook for dependency timeouts.
- **12:48** Found the cause in kafka-broker.
- **13:08** Mitigation applied; error rate falling.
- **13:22** Recovered; incident resolved.

## Root cause

A config change in 8.40.20 cut the timeout to its database to below its normal p99.

Category: dependency timeouts. Component: kafka-broker.

## Contributing factors

- The dependency timeouts alert for kafka-broker had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.
- Dashboards showed averages, which hid the p99.

## Action items

- KAFK-2600 (platform): Add an alert on upstream_timeout_pct for kafka-broker.
- KAFK-5775 (platform): Add a regression test for: a config change in 8.40.20 cut the timeout to its database to below its normal p99.
- KAFK-5438 (platform): Link the runbook from the alert.
