---
service: notifications
updated_at: 2025-12-12
incident_date: 2025-12-05
---
# Postmortem: notifications CPU saturation (2025-12-05)

## Summary

On 2025-12-05, notifications was saturated for 89 minutes. The cause was in kafka-broker.
The incident was sev2 and was opened by `NotificationsCPUSaturated`.

## Impact

- 17% of notifications requests failed or timed out at the peak.
- Callers affected: orders.
- 21,580 customers saw errors; 24 support tickets were opened.

## Timeline

All times UTC.

- **07:30** kafka-broker 8.15.16 deployed by Joshua Diaz.
- **08:08** `NotificationsCPUSaturated` fired; on-call acknowledged.
- **08:27** Checked the notifications runbook for CPU saturation.
- **08:39** Found the cause in kafka-broker.
- **08:49** Mitigation applied; error rate falling.
- **09:37** Recovered; incident resolved.

## Root cause

kafka-broker recomputed a full price table per request after a cache key change in 8.15.16.

Category: CPU saturation. Component: kafka-broker.

## Contributing factors

- The CPU saturation alert for kafka-broker had no runbook link.
- A recent reorg left the alert routed to the wrong team.

## Action items

- NOTI-3696 (growth): Add an alert on cpu_util_pct for kafka-broker.
- NOTI-4201 (platform): Add a regression test for: kafka-broker recomputed a full price table per request after a cache key change in 8.15.16.
- NOTI-3473 (growth): Link the runbook from the alert.
