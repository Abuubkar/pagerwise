---
service: ledger
updated_at: 2026-06-25
---
# Ledger: elevated error rate

Alert: `LedgerErrorRateHigh` fires when the share of 5xx responses in `ledger_error_ratio_pct` stays above its threshold for 5 minutes. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- 5xx responses rise across all endpoints, not one.
- Retries from callers double the request rate.
- Logs show the same error code repeating.

## Likely causes

- **Bad deploy.** A recent release introduced an exception on a common path.
- **Expired credentials.** A rotated secret wasn't picked up and calls to postgres-primary are rejected.
- **Dependency errors passed through.** postgres-primary returns errors and the service doesn't degrade.

The most common cause on ledger is bad deploy: it explained 5 of the
last 8 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_error_ratio_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "bad deploy" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-ERR-612
   ```

4. If `ledger_error_ratio_pct` stays above 6 for 12 minutes, treat it as
   elevated error rate and move to mitigation; below that it usually recovers on its own.
5. Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency.

## Mitigation

1. Roll back the last deploy if it is less than two hours old: `deployctl rollback ledger`.
2. Turn off the feature flag named in the error, if any.
3. If that doesn't help within 10 minutes, set `max_inflight_requests=13` on
   ledger (`configctl set ledger max_inflight_requests 13`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 15 minutes without improvement, or at once if more than
5% of ledger requests are failing. Coordinate in `#ledger-oncall`.
