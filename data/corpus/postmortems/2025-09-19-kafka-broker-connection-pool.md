---
service: kafka-broker
updated_at: 2025-09-25
incident_date: 2025-09-19
---
# Postmortem: kafka-broker connection pool exhaustion (2025-09-19)

## Summary

On 2025-09-19, kafka-broker ran out of database connections for 20 minutes. The cause was in kafka-broker.
The incident was sev2 and was opened by `KafkaBrokerPoolExhausted`.

## Impact

- 48% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 39,409 customers saw errors; 21 support tickets were opened.

## Timeline

All times UTC.

- **02:49** kafka-broker 9.31.14 deployed by Bruce Parker.
- **03:18** `KafkaBrokerPoolExhausted` fired; on-call acknowledged.
- **03:18** Checked the kafka-broker runbook for connection pool exhaustion.
- **03:19** Found the cause in kafka-broker.
- **03:20** Mitigation applied; error rate falling.
- **03:38** Recovered; incident resolved.

## Root cause

9.31.14 of kafka-broker opened a transaction before calling an external API, holding connections for up to 2093 ms.

Category: connection pool exhaustion. Component: kafka-broker.

## Contributing factors

- The connection pool exhaustion alert for kafka-broker had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- KAFK-6181 (platform): Add an alert on pool_wait_ms for kafka-broker.
- KAFK-8188 (platform): Add a regression test for: 9.31.14 of kafka-broker opened a transaction before calling an external api, holding connections for up to 2093 ms.
- KAFK-3727 (platform): Link the runbook from the alert.
