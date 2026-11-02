---
service: inventory
updated_at: 2026-07-19
---
# Inventory: TLS certificate expiry

Alert: `InventoryCertExpiring` fires when a certificate's remaining validity, `inventory_cert_days_left`, drops below its threshold. Inventory is a
supporting-tier service owned by the discovery team; it calls
postgres-primary, and
orders, search call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Pinned intermediate.** A client pins an intermediate that rotated.
- **Renewal job failed.** cert-manager couldn't complete its challenge.

The most common cause on inventory is clock skew: it explained 6 of the
last 10 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `inventory-overview` dashboard and compare `inventory_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history inventory --since 2h`. A deploy in the last hour makes
   "clock skew" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/inventory --since 15m | grep INV-TLS-518
   ```

4. If `inventory_cert_days_left` stays above 3 for 8 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect inventory:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate inventory renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `ocsp_stapling=25` on
   inventory (`configctl set inventory ocsp_stapling 25`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 45 minutes without improvement, or at once if more than
25% of inventory requests are failing. Coordinate in `#discovery-oncall`.
