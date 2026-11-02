---
service: ledger
updated_at: 2026-04-12
incident_date: 2026-04-05
---
# Postmortem: ledger dependency timeouts (2026-04-05)

## Summary

On 2026-04-05, ledger timed out calling its dependencies for 115 minutes. The cause was in kafka-broker.
The incident was sev2 and was opened by `LedgerUpstreamTimeouts`.

## Impact

- 43% of ledger requests failed or timed out at the peak.
- Callers affected: payments.
- 32,336 customers saw errors; 101 support tickets were opened.

## Timeline

All times UTC.

- **13:39** kafka-broker 1.18.9 deployed by Jennifer Cherry.
- **14:16** `LedgerUpstreamTimeouts` fired; on-call acknowledged.
- **14:50** Checked the ledger runbook for dependency timeouts.
- **14:58** Found the cause in kafka-broker.
- **15:20** Mitigation applied; error rate falling.
- **16:11** Recovered; incident resolved.

## Root cause

A config change in 1.18.9 cut the timeout to postgres-primary to below its normal p99.

Category: dependency timeouts. Component: kafka-broker.

## Contributing factors

- The dependency timeouts alert for kafka-broker had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- LEDG-4150 (platform): Add an alert on upstream_timeout_pct for kafka-broker.
- LEDG-5902 (ledger): Add a regression test for: a config change in 1.18.9 cut the timeout to postgres-primary to below its normal p99.
- LEDG-2434 (ledger): Link the runbook from the alert.
