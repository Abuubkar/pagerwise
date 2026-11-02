---
service: card-auth
updated_at: 2026-07-20
---
# Card auth: elevated error rate

Alert: `CardAuthErrorRateHigh` fires when the share of 5xx responses in `card_auth_error_ratio_pct` stays above its threshold for 5 minutes. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Bad deploy.** A recent release introduced an exception on a common path.
- **Dependency errors passed through.** redis-cache returns errors and the service doesn't degrade.
- **Expired credentials.** A rotated secret wasn't picked up and calls to redis-cache are rejected.

The most common cause on card-auth is bad deploy: it explained 20 of the
last 25 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "bad deploy" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-ERR-619
   ```

4. If `card_auth_error_ratio_pct` stays above 9 for 12 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback card-auth`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `retry_budget_pct=46` on
   card-auth (`configctl set card-auth retry_budget_pct 46`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 20 minutes without improvement, or at once if more than
25% of card-auth requests are failing. Coordinate in `#payments-oncall`.
