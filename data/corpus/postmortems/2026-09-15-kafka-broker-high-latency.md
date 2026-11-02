---
service: kafka-broker
updated_at: 2026-09-22
incident_date: 2026-09-15
---
# Postmortem: kafka-broker high p99 latency (2026-09-15)

## Summary

On 2026-09-15, kafka-broker was slow for 38 minutes. The cause was in kafka-broker.
The incident was sev2 and was opened by `KafkaBrokerLatencyHigh`.

## Impact

- 25% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 9,015 customers saw errors; 70 support tickets were opened.

## Timeline

All times UTC.

- **13:26** Routine traffic; nothing unusual in kafka-broker.
- **13:53** `KafkaBrokerLatencyHigh` fired; on-call acknowledged.
- **14:04** Checked the kafka-broker runbook for high p99 latency.
- **14:12** Found the cause in kafka-broker.
- **14:13** Mitigation applied; error rate falling.
- **14:31** Recovered; incident resolved.

## Root cause

A slow query plan in kafka-broker after statistics went stale made p99 climb to 1533 ms.

Category: high p99 latency. Component: kafka-broker.

## Contributing factors

- The high p99 latency alert for kafka-broker had no runbook link.
- A recent reorg left the alert routed to the wrong team.
- Dashboards showed averages, which hid the p99.

## Action items

- KAFK-4921 (platform): Add an alert on p99_latency_ms for kafka-broker.
- KAFK-1675 (platform): Add a regression test for: a slow query plan in kafka-broker after statistics went stale made p99 climb to 1533 ms.
- KAFK-7606 (platform): Link the runbook from the alert.
