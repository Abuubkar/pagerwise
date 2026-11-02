---
service: kafka-broker
updated_at: 2026-03-09
incident_date: 2026-03-04
---
# Postmortem: kafka-broker high p99 latency (2026-03-04)

## Summary

On 2026-03-04, kafka-broker was slow for 109 minutes. The cause was in kafka-broker.
The incident was sev3 and was opened by `KafkaBrokerLatencyHigh`.

## Impact

- 47% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 34,209 customers saw errors; 32 support tickets were opened.

## Timeline

All times UTC.

- **02:22** Routine traffic; nothing unusual in kafka-broker.
- **02:38** `KafkaBrokerLatencyHigh` fired; on-call acknowledged.
- **02:43** Checked the kafka-broker runbook for high p99 latency.
- **03:17** Found the cause in kafka-broker.
- **03:48** Mitigation applied; error rate falling.
- **04:27** Recovered; incident resolved.

## Root cause

A slow query plan in kafka-broker after statistics went stale made p99 climb to 2494 ms.

Category: high p99 latency. Component: kafka-broker.

## Contributing factors

- The high p99 latency alert for kafka-broker had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.
- Dashboards showed averages, which hid the p99.

## Action items

- KAFK-1015 (platform): Add an alert on p99_latency_ms for kafka-broker.
- KAFK-5691 (platform): Add a regression test for: a slow query plan in kafka-broker after statistics went stale made p99 climb to 2494 ms.
- KAFK-1775 (platform): Link the runbook from the alert.
