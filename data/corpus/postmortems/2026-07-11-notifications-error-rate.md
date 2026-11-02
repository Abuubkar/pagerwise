---
service: notifications
updated_at: 2026-07-16
incident_date: 2026-07-11
---
# Postmortem: notifications elevated error rate (2026-07-11)

## Summary

On 2026-07-11, notifications returned errors for 63 minutes. The cause was in notifications.
The incident was sev1 and was opened by `NotificationsErrorRateHigh`.

## Impact

- 26% of notifications requests failed or timed out at the peak.
- Callers affected: orders.
- 19,047 customers saw errors; 53 support tickets were opened.

## Timeline

All times UTC.

- **16:43** Routine traffic; nothing unusual in notifications.
- **17:03** `NotificationsErrorRateHigh` fired; on-call acknowledged.
- **17:19** Checked the notifications runbook for elevated error rate.
- **17:26** Found the cause in notifications.
- **17:30** Mitigation applied; error rate falling.
- **18:06** Recovered; incident resolved.

## Root cause

A credential for notifications was rotated without restarting consumers, so every call was refused.

Category: elevated error rate. Component: notifications.

## Contributing factors

- The elevated error rate alert for notifications had no runbook link.
- The on-call engineer had no access to the database dashboards.

## Action items

- NOTI-5809 (growth): Add an alert on error_ratio_pct for notifications.
- NOTI-1262 (growth): Add a regression test for: a credential for notifications was rotated without restarting consumers, so every call was refused.
- NOTI-9319 (growth): Link the runbook from the alert.
