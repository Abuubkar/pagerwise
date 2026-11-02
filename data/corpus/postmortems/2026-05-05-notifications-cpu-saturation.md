---
service: notifications
updated_at: 2026-05-12
incident_date: 2026-05-05
---
# Postmortem: notifications CPU saturation (2026-05-05)

## Summary

On 2026-05-05, notifications was saturated for 124 minutes. The cause was in notifications.
The incident was sev1 and was opened by `NotificationsCPUSaturated`.

## Impact

- 35% of notifications requests failed or timed out at the peak.
- Callers affected: orders.
- 14,836 customers saw errors; 86 support tickets were opened.

## Timeline

All times UTC.

- **06:45** notifications 1.10.17 deployed by Jason Sherman.
- **07:18** `NotificationsCPUSaturated` fired; on-call acknowledged.
- **07:25** Checked the notifications runbook for CPU saturation.
- **08:07** Found the cause in notifications.
- **08:24** Mitigation applied; error rate falling.
- **09:22** Recovered; incident resolved.

## Root cause

notifications recomputed a full price table per request after a cache key change in 1.10.17.

Category: CPU saturation. Component: notifications.

## Contributing factors

- The CPU saturation alert for notifications had no runbook link.
- The on-call engineer had no access to the database dashboards.
- Dashboards showed averages, which hid the p99.

## Action items

- NOTI-6521 (growth): Add an alert on cpu_util_pct for notifications.
- NOTI-3299 (growth): Add a regression test for: notifications recomputed a full price table per request after a cache key change in 1.10.17.
- NOTI-5534 (growth): Link the runbook from the alert.
