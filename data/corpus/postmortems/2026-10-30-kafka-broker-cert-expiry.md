---
service: kafka-broker
updated_at: 2026-11-01
incident_date: 2026-10-30
---
# Postmortem: kafka-broker TLS certificate expiry (2026-10-30)

## Summary

On 2026-10-30, kafka-broker rejected TLS connections for 69 minutes. The cause was in kafka-broker.
The incident was sev2 and was opened by `KafkaBrokerCertExpiring`.

## Impact

- 47% of kafka-broker requests failed or timed out at the peak.
- Callers affected: ledger, notifications, payments.
- 3,522 customers saw errors; 34 support tickets were opened.

## Timeline

All times UTC.

- **13:42** Routine traffic; nothing unusual in kafka-broker.
- **13:54** `KafkaBrokerCertExpiring` fired; on-call acknowledged.
- **13:58** Checked the kafka-broker runbook for TLS certificate expiry.
- **14:07** Found the cause in kafka-broker.
- **14:23** Mitigation applied; error rate falling.
- **15:03** Recovered; incident resolved.

## Root cause

The renewal job for kafka-broker failed for 3718 days because its DNS challenge record was deleted.

Category: TLS certificate expiry. Component: kafka-broker.

## Contributing factors

- The TLS certificate expiry alert for kafka-broker had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.
- Dashboards showed averages, which hid the p99.

## Action items

- KAFK-5843 (platform): Add an alert on cert_days_left for kafka-broker.
- KAFK-2399 (platform): Add a regression test for: the renewal job for kafka-broker failed for 3718 days because its dns challenge record was deleted.
- KAFK-3781 (platform): Link the runbook from the alert.
