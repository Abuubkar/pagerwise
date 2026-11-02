---
service: ledger
updated_at: 2025-09-15
incident_date: 2025-09-08
---
# Postmortem: ledger queue backlog (2025-09-08)

## Summary

On 2025-09-08, ledger fell behind for 28 minutes. The cause was in postgres-primary.
The incident was sev3 and was opened by `LedgerConsumerLagHigh`.

## Impact

- 34% of ledger requests failed or timed out at the peak.
- Callers affected: payments.
- 38,702 customers saw errors; 25 support tickets were opened.

## Timeline

All times UTC.

- **01:29** postgres-primary 8.34.2 deployed by Jacqueline Kelley.
- **01:50** `LedgerConsumerLagHigh` fired; on-call acknowledged.
- **01:57** Checked the ledger runbook for queue backlog.
- **02:02** Found the cause in postgres-primary.
- **02:06** Mitigation applied; error rate falling.
- **02:18** Recovered; incident resolved.

## Root cause

8.34.2 of postgres-primary made an external call per message, cutting throughput by two thirds.

Category: queue backlog. Component: postgres-primary.

## Contributing factors

- The queue backlog alert for postgres-primary had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- LEDG-4150 (ledger): Add an alert on consumer_lag_msgs for postgres-primary.
- LEDG-3960 (platform): Add a regression test for: 8.34.2 of postgres-primary made an external call per message, cutting throughput by two thirds.
- LEDG-6944 (platform): Link the runbook from the alert.
