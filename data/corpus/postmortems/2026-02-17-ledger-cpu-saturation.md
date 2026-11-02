---
service: ledger
updated_at: 2026-02-23
incident_date: 2026-02-17
---
# Postmortem: ledger CPU saturation (2026-02-17)

## Summary

On 2026-02-17, ledger was saturated for 20 minutes. The cause was in ledger.
The incident was sev3 and was opened by `LedgerCPUSaturated`.

## Impact

- 3% of ledger requests failed or timed out at the peak.
- Callers affected: payments.
- 9,373 customers saw errors; 32 support tickets were opened.

## Timeline

All times UTC.

- **08:35** ledger 2.17.6 deployed by Jordan Johnson.
- **09:12** `LedgerCPUSaturated` fired; on-call acknowledged.
- **09:12** Checked the ledger runbook for CPU saturation.
- **09:19** Found the cause in ledger.
- **09:24** Mitigation applied; error rate falling.
- **09:32** Recovered; incident resolved.

## Root cause

ledger recomputed a full price table per request after a cache key change in 2.17.6.

Category: CPU saturation. Component: ledger.

## Contributing factors

- The CPU saturation alert for ledger had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- LEDG-4969 (ledger): Add an alert on cpu_util_pct for ledger.
- LEDG-7900 (ledger): Add a regression test for: ledger recomputed a full price table per request after a cache key change in 2.17.6.
- LEDG-4745 (ledger): Link the runbook from the alert.
