---
service: notifications
updated_at: 2026-02-20
---
# Notifications: TLS certificate expiry

Alert: `NotificationsCertExpiring` fires when a certificate's remaining validity, `notifications_cert_days_left`, drops below its threshold. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Pinned intermediate.** A client pins an intermediate that rotated.

The most common cause on notifications is clock skew: it explained 9 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "clock skew" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-TLS-302
   ```

4. If `notifications_cert_days_left` stays above 8 for 10 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect notifications:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate notifications renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `cert_renew_before_days=53` on
   notifications (`configctl set notifications cert_renew_before_days 53`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 30 minutes without improvement, or at once if more than
10% of notifications requests are failing. Coordinate in `#growth-oncall`.
