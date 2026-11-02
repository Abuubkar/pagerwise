---
service: kafka-broker
updated_at: 2026-05-20
incident_date: 2026-05-17
---
# Postmortem: kafka-broker memory pressure and OOM kills (2026-05-17)

## Summary

On 2026-05-17, kafka-broker kept restarting for 101 minutes. The cause was in kafka-broker.
The incident was sev3 and was opened by `KafkaBrokerMemoryPressure`.

## Impact

- 33% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 38,477 customers saw errors; 64 support tickets were opened.

## Timeline

All times UTC.

- **01:31** kafka-broker 8.33.7 deployed by Kelly Golden.
- **01:53** `KafkaBrokerMemoryPressure` fired; on-call acknowledged.
- **01:58** Checked the kafka-broker runbook for memory pressure and OOM kills.
- **02:05** Found the cause in kafka-broker.
- **02:15** Mitigation applied; error rate falling.
- **03:34** Recovered; incident resolved.

## Root cause

A cache added in 8.33.7 of kafka-broker had no eviction, growing to 3650 MB per pod.

Category: memory pressure and OOM kills. Component: kafka-broker.

## Contributing factors

- The memory pressure and OOM kills alert for kafka-broker had no runbook link.
- A recent reorg left the alert routed to the wrong team.

## Action items

- KAFK-2999 (platform): Add an alert on rss_pct_of_limit for kafka-broker.
- KAFK-7646 (platform): Add a regression test for: a cache added in 8.33.7 of kafka-broker had no eviction, growing to 3650 mb per pod.
- KAFK-9873 (platform): Link the runbook from the alert.
