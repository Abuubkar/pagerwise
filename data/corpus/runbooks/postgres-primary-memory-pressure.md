---
service: postgres-primary
updated_at: 2026-03-10
---
# Postgres primary: memory pressure and OOM kills

Alert: `PostgresPrimaryMemoryPressure` fires when container memory, `postgres_primary_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Large payloads.** A few very large requests allocate far more than usual.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.

The most common cause on postgres-primary is memory leak in a recent release: it explained 22 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "memory leak in a recent release" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-MEM-340
   ```

4. If `postgres_primary_rss_pct_of_limit` stays above 82 for 7 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/postgres-primary`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `gc_target_pct=50` on
   postgres-primary (`configctl set postgres-primary gc_target_pct 50`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 45 minutes without improvement, or at once if more than
5% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
