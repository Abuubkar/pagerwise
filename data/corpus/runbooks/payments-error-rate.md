---
service: payments
updated_at: 2026-04-28
---
# Payments: elevated error rate

Alert: `PaymentsErrorRateHigh` fires when the share of 5xx responses in `payments_error_ratio_pct` stays above its threshold for 5 minutes. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Bad deploy.** A recent release introduced an exception on a common path.
- **Expired credentials.** A rotated secret wasn't picked up and calls to card-auth are rejected.
- **Dependency errors passed through.** card-auth returns errors and the service doesn't degrade.

The most common cause on payments is bad deploy: it explained 11 of the
last 19 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "bad deploy" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-ERR-298
   ```

4. If `payments_error_ratio_pct` stays above 9 for 7 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback payments`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `max_inflight_requests=40` on
   payments (`configctl set payments max_inflight_requests 40`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 20 minutes without improvement, or at once if more than
5% of payments requests are failing. Coordinate in `#payments-oncall`.
