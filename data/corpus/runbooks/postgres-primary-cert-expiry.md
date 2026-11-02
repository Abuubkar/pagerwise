---
service: postgres-primary
updated_at: 2025-11-05
---
# Postgres primary: TLS certificate expiry

Alert: `PostgresPrimaryCertExpiring` fires when a certificate's remaining validity, `postgres_primary_cert_days_left`, drops below its threshold. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Pinned intermediate.** A client pins an intermediate that rotated.
- **Clock skew.** A node's clock is far enough off to reject valid certificates.

The most common cause on postgres-primary is renewal job failed: it explained 8 of the
last 11 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "renewal job failed" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-TLS-468
   ```

4. If `postgres_primary_cert_days_left` stays above 5 for 7 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect postgres-primary:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate postgres-primary renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `cert_renew_before_days=40` on
   postgres-primary (`configctl set postgres-primary cert_renew_before_days 40`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
25% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
