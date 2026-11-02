---
service: ledger
updated_at: 2026-05-02
---
# Ledger: dependency timeouts

Alert: `LedgerUpstreamTimeouts` fires when the share of calls to a dependency that time out, `ledger_upstream_timeout_pct`, stays above its threshold for 5 minutes. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- Timeouts concentrate on calls to postgres-primary.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Network path.** Packet loss between zones adds retransmits.
- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Dependency degraded.** postgres-primary itself is slow or partially down.

The most common cause on ledger is network path: it explained 9 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "network path" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-DEP-660
   ```

4. If `ledger_upstream_timeout_pct` stays above 6 for 8 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check postgres-primary's own dashboard before changing anything in ledger.

## Mitigation

1. Open the circuit breaker for postgres-primary if the feature can degrade.
2. Fail over calls to the standby region for postgres-primary if one exists.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=17` on
   ledger (`configctl set ledger circuit_breaker_threshold 17`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 15 minutes without improvement, or at once if more than
20% of ledger requests are failing. Coordinate in `#ledger-oncall`.
