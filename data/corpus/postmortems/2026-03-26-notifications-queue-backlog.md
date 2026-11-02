---
service: notifications
updated_at: 2026-04-03
incident_date: 2026-03-26
---
# Postmortem: notifications queue backlog (2026-03-26)

## Summary

On 2026-03-26, notifications fell behind for 96 minutes. The cause was in notifications.
The incident was sev3 and was opened by `NotificationsConsumerLagHigh`.

## Impact

- 14% of notifications requests failed or timed out at the peak.
- Callers affected: orders.
- 35,670 customers saw errors; 41 support tickets were opened.

## Timeline

All times UTC.

- **09:34** Routine traffic; nothing unusual in notifications.
- **10:10** `NotificationsConsumerLagHigh` fired; on-call acknowledged.
- **10:23** Checked the notifications runbook for queue backlog.
- **10:43** Found the cause in notifications.
- **11:22** Mitigation applied; error rate falling.
- **11:46** Recovered; incident resolved.

## Root cause

A poison message in notifications's topic blocked partition 3989 for 40 minutes.

Category: queue backlog. Component: notifications.

## Contributing factors

- The queue backlog alert for notifications had no runbook link.
- Two teams investigated the same symptom without knowing it.
- Dashboards showed averages, which hid the p99.

## Action items

- NOTI-2490 (growth): Add an alert on consumer_lag_msgs for notifications.
- NOTI-5119 (growth): Add a regression test for: a poison message in notifications's topic blocked partition 3989 for 40 minutes.
- NOTI-2280 (growth): Link the runbook from the alert.
