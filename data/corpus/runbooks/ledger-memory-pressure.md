---
service: ledger
updated_at: 2025-11-04
---
# Ledger: memory pressure and OOM kills

Alert: `LedgerMemoryPressure` fires when container memory, `ledger_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Large payloads.** A few very large requests allocate far more than usual.
- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.

The most common cause on ledger is large payloads: it explained 13 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "large payloads" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-MEM-804
   ```

4. If `ledger_rss_pct_of_limit` stays above 96 for 7 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/ledger`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `cache_max_entries=64` on
   ledger (`configctl set ledger cache_max_entries 64`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 20 minutes without improvement, or at once if more than
25% of ledger requests are failing. Coordinate in `#ledger-oncall`.
