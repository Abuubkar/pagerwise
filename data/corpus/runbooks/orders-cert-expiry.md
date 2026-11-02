---
service: orders
updated_at: 2026-04-26
---
# Orders: TLS certificate expiry

Alert: `OrdersCertExpiring` fires when a certificate's remaining validity, `orders_cert_days_left`, drops below its threshold. Orders is a
core-tier service owned by the commerce team; it calls
payments, inventory, notifications, postgres-primary, and
api-gateway call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Pinned intermediate.** A client pins an intermediate that rotated.

The most common cause on orders is renewal job failed: it explained 22 of the
last 29 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `orders-overview` dashboard and compare `orders_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history orders --since 2h`. A deploy in the last hour makes
   "renewal job failed" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n commerce logs deploy/orders --since 15m | grep ORD-TLS-415
   ```

4. If `orders_cert_days_left` stays above 13 for 10 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect orders:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate orders renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `ocsp_stapling=17` on
   orders (`configctl set orders ocsp_stapling 17`) and restart one pod at a
   time.

## Escalation

Page the commerce secondary after 45 minutes without improvement, or at once if more than
10% of orders requests are failing. Coordinate in `#commerce-oncall`.
