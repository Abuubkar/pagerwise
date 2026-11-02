---
service: api-gateway
updated_at: 2026-04-17
---
# Api gateway: TLS certificate expiry

Alert: `ApiGatewayCertExpiring` fires when a certificate's remaining validity, `api_gateway_cert_days_left`, drops below its threshold. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Pinned intermediate.** A client pins an intermediate that rotated.

The most common cause on api-gateway is renewal job failed: it explained 30 of the
last 30 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "renewal job failed" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-TLS-762
   ```

4. If `api_gateway_cert_days_left` stays above 3 for 7 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect api-gateway:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate api-gateway renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `ocsp_stapling=45` on
   api-gateway (`configctl set api-gateway ocsp_stapling 45`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
5% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
