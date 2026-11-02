---
service: payments
updated_at: 2026-11-01
incident_date: 2026-10-30
---
# Postmortem: payments dependency timeouts (2026-10-30)

## Summary

On 2026-10-30, payments timed out calling its dependencies for 137 minutes. The cause was in ledger.
The incident was sev2 and was opened by `PaymentsUpstreamTimeouts`.

## Impact

- 54% of payments requests failed or timed out at the peak.
- Callers affected: api-gateway, orders.
- 14,151 customers saw errors; 120 support tickets were opened.

## Timeline

All times UTC.

- **16:51** Routine traffic; nothing unusual in ledger.
- **17:12** `PaymentsUpstreamTimeouts` fired; on-call acknowledged.
- **17:59** Checked the payments runbook for dependency timeouts.
- **18:40** Found the cause in ledger.
- **19:18** Mitigation applied; error rate falling.
- **19:29** Recovered; incident resolved.

## Root cause

ledger timed out because its connection to card-auth pinned to a single failing node.

Category: dependency timeouts. Component: ledger.

## Contributing factors

- The dependency timeouts alert for ledger had no runbook link.
- The on-call engineer had no access to the database dashboards.
- Dashboards showed averages, which hid the p99.

## Action items

- PAYM-3716 (ledger): Add an alert on upstream_timeout_pct for ledger.
- PAYM-2325 (payments): Add a regression test for: ledger timed out because its connection to card-auth pinned to a single failing node.
- PAYM-2713 (payments): Link the runbook from the alert.
