---
service: card-auth
updated_at: 2026-10-23
---
# Card auth: TLS certificate expiry

Alert: `CardAuthCertExpiring` fires when a certificate's remaining validity, `card_auth_cert_days_left`, drops below its threshold. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Pinned intermediate.** A client pins an intermediate that rotated.

The most common cause on card-auth is clock skew: it explained 10 of the
last 16 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "clock skew" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-TLS-158
   ```

4. If `card_auth_cert_days_left` stays above 4 for 7 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect card-auth:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate card-auth renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `ocsp_stapling=13` on
   card-auth (`configctl set card-auth ocsp_stapling 13`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 30 minutes without improvement, or at once if more than
5% of card-auth requests are failing. Coordinate in `#payments-oncall`.
