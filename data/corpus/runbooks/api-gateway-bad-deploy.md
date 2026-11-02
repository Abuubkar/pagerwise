---
service: api-gateway
updated_at: 2026-09-14
---
# Api gateway: regression after a deploy

Alert: `ApiGatewayPostDeployErrors` fires when errors in the 30 minutes after a deploy, `api_gateway_post_deploy_error_pct`, exceed their threshold. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- Errors start within minutes of a deploy finishing.
- Only pods on the new version show errors.
- Canary metrics were borderline but passed.

## Likely causes

- **Code regression.** The new release breaks a path the tests don't cover.
- **Schema mismatch.** The release reads a column a migration hasn't added yet.
- **Config drift.** The release expects a setting that isn't present in production.

The most common cause on api-gateway is code regression: it explained 8 of the
last 10 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_post_deploy_error_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "code regression" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-DEPLOY-811
   ```

4. If `api_gateway_post_deploy_error_pct` stays above 6 for 8 minutes, treat it as
   regression after a deploy and move to mitigation; below that it usually recovers on its own.
5. Compare error rates between pods on the old and new version.

## Mitigation

1. Roll back: `deployctl rollback api-gateway`; don't wait to debug.
2. Freeze deploys for api-gateway.
3. If that doesn't help within 10 minutes, set `deploy_batch_size=40` on
   api-gateway (`configctl set api-gateway deploy_batch_size 40`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
5% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
