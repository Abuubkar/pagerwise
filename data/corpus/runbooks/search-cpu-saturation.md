---
service: search
updated_at: 2026-04-24
---
# Search: CPU saturation

Alert: `SearchCPUSaturated` fires when CPU utilisation, `search_cpu_util_pct`, stays above its threshold for 10 minutes. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Hot loop in a release.** A recent change made a common path far more expensive.
- **Traffic spike.** Legitimate load above what the current replica count serves.

The most common cause on search is noisy neighbour: it explained 12 of the
last 14 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "noisy neighbour" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-CPU-941
   ```

4. If `search_cpu_util_pct` stays above 86 for 7 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `worker_threads=7` on
   search (`configctl set search worker_threads 7`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 45 minutes without improvement, or at once if more than
10% of search requests are failing. Coordinate in `#discovery-oncall`.
