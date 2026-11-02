---
service: kafka-broker
updated_at: 2025-12-15
---
# Kafka broker: TLS certificate expiry

Alert: `KafkaBrokerCertExpiring` fires when a certificate's remaining validity, `kafka_broker_cert_days_left`, drops below its threshold. Kafka broker is a
data-tier service owned by the platform team; it calls
no other internal services, and
ledger, notifications, payments call it.

## Symptoms

- Handshake failures from clients with strict validation.
- Errors start at the same minute everywhere.
- Internal calls fail while external ones work, or the reverse.

## Likely causes

- **Clock skew.** A node's clock is far enough off to reject valid certificates.
- **Pinned intermediate.** A client pins an intermediate that rotated.
- **Renewal job failed.** cert-manager couldn't complete its challenge.

The most common cause on kafka-broker is clock skew: it explained 20 of the
last 27 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `kafka-broker-overview` dashboard and compare `kafka_broker_cert_days_left` with the
   same hour last week.
2. Check recent changes: `deployctl history kafka-broker --since 2h`. A deploy in the last hour makes
   "clock skew" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/kafka-broker --since 15m | grep KAF-TLS-865
   ```

4. If `kafka_broker_cert_days_left` stays above 14 for 3 minutes, treat it as
   TLS certificate expiry and move to mitigation; below that it usually recovers on its own.
5. Check expiry with `openssl s_client -connect kafka-broker:443 | openssl x509 -noout -enddate`.

## Mitigation

1. Force renewal: `kubectl -n platform annotate certificate kafka-broker renew=now`.
2. Restart pods so they load the new certificate.
3. If that doesn't help within 10 minutes, set `cert_renew_before_days=16` on
   kafka-broker (`configctl set kafka-broker cert_renew_before_days 16`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
20% of kafka-broker requests are failing. Coordinate in `#platform-oncall`.
