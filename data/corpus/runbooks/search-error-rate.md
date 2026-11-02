---
service: search
updated_at: 2026-05-24
---
# Search: elevated error rate

Alert: `SearchErrorRateHigh` fires when the share of 5xx responses in `search_error_ratio_pct` stays above its threshold for 5 minutes. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Bad deploy.** A recent release introduced an exception on a common path.
- **Expired credentials.** A rotated secret wasn't picked up and calls to inventory are rejected.
- **Dependency errors passed through.** inventory returns errors and the service doesn't degrade.

The most common cause on search is bad deploy: it explained 27 of the
last 30 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "bad deploy" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-ERR-826
   ```

4. If `search_error_ratio_pct` stays above 8 for 3 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback search`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `retry_budget_pct=13` on
   search (`configctl set search retry_budget_pct 13`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 15 minutes without improvement, or at once if more than
5% of search requests are failing. Coordinate in `#discovery-oncall`.
