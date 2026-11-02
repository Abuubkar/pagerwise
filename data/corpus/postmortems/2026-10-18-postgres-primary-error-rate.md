---
service: postgres-primary
updated_at: 2026-10-23
incident_date: 2026-10-18
---
# Postmortem: postgres-primary elevated error rate (2026-10-18)

## Summary

On 2026-10-18, postgres-primary returned errors for 64 minutes. The cause was in postgres-primary.
The incident was sev3 and was opened by `PostgresPrimaryErrorRateHigh`.

## Impact

- 10% of postgres-primary requests failed or timed out at the peak.
- Callers affected: auth, inventory, ledger, orders.
- 34,915 customers saw errors; 76 support tickets were opened.

## Timeline

All times UTC.

- **13:28** Routine traffic; nothing unusual in postgres-primary.
- **13:57** `PostgresPrimaryErrorRateHigh` fired; on-call acknowledged.
- **14:18** Checked the postgres-primary runbook for elevated error rate.
- **14:30** Found the cause in postgres-primary.
- **14:35** Mitigation applied; error rate falling.
- **15:01** Recovered; incident resolved.

## Root cause

A credential for postgres-primary was rotated without restarting consumers, so every call was refused.

Category: elevated error rate. Component: postgres-primary.

## Contributing factors

- The elevated error rate alert for postgres-primary had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- POST-6352 (platform): Add an alert on error_ratio_pct for postgres-primary.
- POST-8377 (platform): Add a regression test for: a credential for postgres-primary was rotated without restarting consumers, so every call was refused.
- POST-3777 (platform): Link the runbook from the alert.
