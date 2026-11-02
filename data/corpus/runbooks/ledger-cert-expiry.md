---
service: ledger
updated_at: 2026-05-29
---
# Ledger: TLS certificate expiry

Alert: `LedgerCertExpiring` fires when a certificate's remaining validity, `ledger_cert_days_left`, drops below its threshold. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Pinned intermediate.** A client pins an intermediate that rotated.

The most common cause on ledger is clock skew: it explained 12 of the
last 17 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "clock skew" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-TLS-509
   ```

4. If `ledger_cert_days_left` stays above 4 for 5 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect ledger:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate ledger renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `ocsp_stapling=4` on
   ledger (`configctl set ledger ocsp_stapling 4`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 15 minutes without improvement, or at once if more than
10% of ledger requests are failing. Coordinate in `#ledger-oncall`.
