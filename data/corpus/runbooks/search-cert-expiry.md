---
service: search
updated_at: 2026-02-21
---
# Search: TLS certificate expiry

Alert: `SearchCertExpiring` fires when a certificate's remaining validity, `search_cert_days_left`, drops below its threshold. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Pinned intermediate.** A client pins an intermediate that rotated.

The most common cause on search is renewal job failed: it explained 13 of the
last 21 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "renewal job failed" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-TLS-832
   ```

4. If `search_cert_days_left` stays above 4 for 12 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect search:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate search renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `tls_min_version=63` on
   search (`configctl set search tls_min_version 63`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 45 minutes without improvement, or at once if more than
10% of search requests are failing. Coordinate in `#discovery-oncall`.
