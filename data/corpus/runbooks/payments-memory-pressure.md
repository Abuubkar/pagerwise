---
service: payments
updated_at: 2025-10-27
---
# Payments: memory pressure and OOM kills

Alert: `PaymentsMemoryPressure` fires when container memory, `payments_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Large payloads.** A few very large requests allocate far more than usual.

The most common cause on payments is unbounded cache: it explained 9 of the
last 10 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "unbounded cache" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-MEM-589
   ```

4. If `payments_rss_pct_of_limit` stays above 92 for 6 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/payments`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `cache_max_entries=29` on
   payments (`configctl set payments cache_max_entries 29`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 45 minutes without improvement, or at once if more than
25% of payments requests are failing. Coordinate in `#payments-oncall`.
