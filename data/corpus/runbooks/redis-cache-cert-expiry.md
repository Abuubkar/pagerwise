---
service: redis-cache
updated_at: 2025-10-13
---
# Redis cache: TLS certificate expiry

Alert: `RedisCacheCertExpiring` fires when a certificate's remaining validity, `redis_cache_cert_days_left`, drops below its threshold. Redis cache is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, card-auth, search call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Pinned intermediate.** A client pins an intermediate that rotated.
- **Renewal job failed.** cert-manager couldn't complete its challenge.
- **Clock skew.** A node's clock is far enough off to reject valid certificates.

The most common cause on redis-cache is pinned intermediate: it explained 8 of the
last 8 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `redis-cache-overview` dashboard and compare `redis_cache_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history redis-cache --since 2h`. A deploy in the last hour makes
   "pinned intermediate" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/redis-cache --since 15m | grep RED-TLS-477
   ```

4. If `redis_cache_cert_days_left` stays above 8 for 6 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect redis-cache:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate redis-cache renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `tls_min_version=53` on
   redis-cache (`configctl set redis-cache tls_min_version 53`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
25% of redis-cache requests are failing. Coordinate in `#platform-oncall`.
