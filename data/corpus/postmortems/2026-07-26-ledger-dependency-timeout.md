---
service: ledger
updated_at: 2026-08-02
incident_date: 2026-07-26
---
# Postmortem: ledger dependency timeouts (2026-07-26)

## Summary

On 2026-07-26, ledger timed out calling its dependencies for 131 minutes. The cause was in postgres-primary.
The incident was sev2 and was opened by `LedgerUpstreamTimeouts`.

## Impact

- 51% of ledger requests failed or timed out at the peak.
- Callers affected: payments.
- 29,390 customers saw errors; 12 support tickets were opened.

## Timeline

All times UTC.

- **12:21** Routine traffic; nothing unusual in postgres-primary.
- **12:30** `LedgerUpstreamTimeouts` fired; on-call acknowledged.
- **12:39** Checked the ledger runbook for dependency timeouts.
- **13:10** Found the cause in postgres-primary.
- **13:19** Mitigation applied; error rate falling.
- **14:41** Recovered; incident resolved.

## Root cause

postgres-primary timed out because its connection to postgres-primary pinned to a single failing node.

Category: dependency timeouts. Component: postgres-primary.

## Contributing factors

- The dependency timeouts alert for postgres-primary had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- LEDG-2231 (platform): Add an alert on upstream_timeout_pct for postgres-primary.
- LEDG-6566 (platform): Add a regression test for: postgres-primary timed out because its connection to postgres-primary pinned to a single failing node.
- LEDG-4831 (platform): Link the runbook from the alert.
