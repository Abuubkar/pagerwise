---
service: auth
updated_at: 2026-09-15
---
# Auth: TLS certificate expiry

Alert: `AuthCertExpiring` fires when a certificate's remaining validity, `auth_cert_days_left`, drops below its threshold. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Pinned intermediate.** A client pins an intermediate that rotated.
- **Renewal job failed.** cert-manager couldn't complete its challenge.

The most common cause on auth is clock skew: it explained 26 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "clock skew" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-TLS-250
   ```

4. If `auth_cert_days_left` stays above 11 for 8 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect auth:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate auth renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `ocsp_stapling=36` on
   auth (`configctl set auth ocsp_stapling 36`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 30 minutes without improvement, or at once if more than
20% of auth requests are failing. Coordinate in `#identity-oncall`.
