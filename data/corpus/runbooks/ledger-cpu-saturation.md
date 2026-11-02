---
service: ledger
updated_at: 2026-08-09
---
# Ledger: CPU saturation

Alert: `LedgerCPUSaturated` fires when CPU utilisation, `ledger_cpu_util_pct`, stays above its threshold for 10 minutes. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Hot loop in a release.** A recent change made a common path far more expensive.
- **Traffic spike.** Legitimate load above what the current replica count serves.

The most common cause on ledger is noisy neighbour: it explained 11 of the
last 21 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "noisy neighbour" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-CPU-957
   ```

4. If `ledger_cpu_util_pct` stays above 86 for 3 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `autoscale_max_replicas=2` on
   ledger (`configctl set ledger autoscale_max_replicas 2`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 15 minutes without improvement, or at once if more than
25% of ledger requests are failing. Coordinate in `#ledger-oncall`.
