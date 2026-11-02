---
service: payments
updated_at: 2026-03-03
---
# Payments: TLS certificate expiry

Alert: `PaymentsCertExpiring` fires when a certificate's remaining validity, `payments_cert_days_left`, drops below its threshold. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Pinned intermediate.** A client pins an intermediate that rotated.
- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Renewal job failed.** cert-manager couldn't complete its challenge.

The most common cause on payments is pinned intermediate: it explained 11 of the
last 12 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "pinned intermediate" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-TLS-723
   ```

4. If `payments_cert_days_left` stays above 10 for 5 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect payments:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate payments renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `cert_renew_before_days=51` on
   payments (`configctl set payments cert_renew_before_days 51`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 15 minutes without improvement, or at once if more than
5% of payments requests are failing. Coordinate in `#payments-oncall`.
