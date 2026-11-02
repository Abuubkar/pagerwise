---
service: postgres-primary
updated_at: 2025-12-28
---
# Postgres primary: CPU saturation

Alert: `PostgresPrimaryCPUSaturated` fires when CPU utilisation, `postgres_primary_cpu_util_pct`, stays above its threshold for 10 minutes. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Hot loop in a release.** A recent change made a common path far more expensive.
- **Traffic spike.** Legitimate load above what the current replica count serves.
- **Noisy neighbour.** Another workload on the same nodes takes CPU.

The most common cause on postgres-primary is hot loop in a release: it explained 7 of the
last 10 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "hot loop in a release" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-CPU-885
   ```

4. If `postgres_primary_cpu_util_pct` stays above 90 for 7 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `autoscale_max_replicas=41` on
   postgres-primary (`configctl set postgres-primary autoscale_max_replicas 41`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
20% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
