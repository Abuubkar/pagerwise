---
service: api-gateway
updated_at: 2026-01-15
---
# Api gateway: elevated error rate

Alert: `ApiGatewayErrorRateHigh` fires when the share of 5xx responses in `api_gateway_error_ratio_pct` stays above its threshold for 5 minutes. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Expired credentials.** A rotated secret wasn't picked up and calls to auth are rejected.
- **Dependency errors passed through.** auth returns errors and the service doesn't degrade.
- **Bad deploy.** A recent release introduced an exception on a common path.

The most common cause on api-gateway is expired credentials: it explained 5 of the
last 9 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "expired credentials" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-ERR-528
   ```

4. If `api_gateway_error_ratio_pct` stays above 3 for 10 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback api-gateway`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `retry_budget_pct=17` on
   api-gateway (`configctl set api-gateway retry_budget_pct 17`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
5% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
