---
service: orders
updated_at: 2025-12-23
incident_date: 2025-12-21
---
# Postmortem: orders elevated error rate (2025-12-21)

## Summary

On 2025-12-21, orders returned errors for 41 minutes. The cause was in payments.
The incident was sev1 and was opened by `OrdersErrorRateHigh`.

## Impact

- 59% of orders requests failed or timed out at the peak.
- Callers affected: api-gateway.
- 18,487 customers saw errors; 38 support tickets were opened.

## Timeline

All times UTC.

- **14:30** payments 3.38.14 deployed by Angela Cole.
- **14:48** `OrdersErrorRateHigh` fired; on-call acknowledged.
- **14:48** Checked the orders runbook for elevated error rate.
- **15:06** Found the cause in payments.
- **15:11** Mitigation applied; error rate falling.
- **15:29** Recovered; incident resolved.

## Root cause

3.38.14 of payments sent a null currency on refunds, which the validation layer rejected.

Category: elevated error rate. Component: payments.

## Contributing factors

- The elevated error rate alert for payments had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- ORDE-6061 (payments): Add an alert on error_ratio_pct for payments.
- ORDE-2851 (commerce): Add a regression test for: 3.38.14 of payments sent a null currency on refunds, which the validation layer rejected.
- ORDE-6316 (payments): Link the runbook from the alert.
