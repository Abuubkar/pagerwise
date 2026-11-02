---
service: payments
updated_at: 2026-11-01
incident_date: 2026-10-30
---
# Postmortem: payments high p99 latency (2026-10-30)

## Summary

On 2026-10-30, payments was slow for 148 minutes. The cause was in payments.
The incident was sev1 and was opened by `PaymentsLatencyHigh`.

## Impact

- 4% of payments requests failed or timed out at the peak.
- Callers affected: api-gateway, orders.
- 2,336 customers saw errors; 108 support tickets were opened.

## Timeline

All times UTC.

- **01:50** Routine traffic; nothing unusual in payments.
- **02:08** `PaymentsLatencyHigh` fired; on-call acknowledged.
- **02:24** Checked the payments runbook for high p99 latency.
- **02:35** Found the cause in payments.
- **03:11** Mitigation applied; error rate falling.
- **04:36** Recovered; incident resolved.

## Root cause

A slow query plan in payments after statistics went stale made p99 climb to 2989 ms.

Category: high p99 latency. Component: payments.

## Contributing factors

- The high p99 latency alert for payments had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- PAYM-8817 (payments): Add an alert on p99_latency_ms for payments.
- PAYM-3173 (payments): Add a regression test for: a slow query plan in payments after statistics went stale made p99 climb to 2989 ms.
- PAYM-4358 (payments): Link the runbook from the alert.
