---
service: kafka-broker
updated_at: 2026-04-23
incident_date: 2026-04-16
---
# Postmortem: kafka-broker high p99 latency (2026-04-16)

## Summary

On 2026-04-16, kafka-broker was slow for 48 minutes. The cause was in kafka-broker.
The incident was sev1 and was opened by `KafkaBrokerLatencyHigh`.

## Impact

- 36% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 36,365 customers saw errors; 62 support tickets were opened.

## Timeline

All times UTC.

- **08:41** kafka-broker 7.10.18 deployed by Catherine Perkins.
- **09:17** `KafkaBrokerLatencyHigh` fired; on-call acknowledged.
- **09:26** Checked the kafka-broker runbook for high p99 latency.
- **09:34** Found the cause in kafka-broker.
- **09:52** Mitigation applied; error rate falling.
- **10:05** Recovered; incident resolved.

## Root cause

kafka-broker held a lock across a network call introduced in 7.10.18, serializing writes.

Category: high p99 latency. Component: kafka-broker.

## Contributing factors

- The high p99 latency alert for kafka-broker had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- KAFK-4834 (platform): Add an alert on p99_latency_ms for kafka-broker.
- KAFK-1943 (platform): Add a regression test for: kafka-broker held a lock across a network call introduced in 7.10.18, serializing writes.
- KAFK-8623 (platform): Link the runbook from the alert.
