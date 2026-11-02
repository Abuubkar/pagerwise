---
service: auth
updated_at: 2026-08-15
---
# Auth: elevated error rate

Alert: `AuthErrorRateHigh` fires when the share of 5xx responses in `auth_error_ratio_pct` stays above its threshold for 5 minutes. Auth is a
core-tier service owned by the identity team; it calls
redis-cache, postgres-primary, and
api-gateway call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Bad deploy.** A recent release introduced an exception on a common path.
- **Dependency errors passed through.** redis-cache returns errors and the service doesn't degrade.
- **Expired credentials.** A rotated secret wasn't picked up and calls to redis-cache are rejected.

The most common cause on auth is bad deploy: it explained 9 of the
last 15 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `auth-overview` dashboard and compare `auth_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history auth --since 2h`. A deploy in the last hour makes
   "bad deploy" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n identity logs deploy/auth --since 15m | grep AUT-ERR-823
   ```

4. If `auth_error_ratio_pct` stays above 15 for 7 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback auth`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=24` on
   auth (`configctl set auth circuit_breaker_threshold 24`) and restart one pod at a
   time.

## Escalation

Page the identity secondary after 20 minutes without improvement, or at once if more than
10% of auth requests are failing. Coordinate in `#identity-oncall`.
