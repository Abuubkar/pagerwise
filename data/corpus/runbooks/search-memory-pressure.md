---
service: search
updated_at: 2026-03-30
---
# Search: memory pressure and OOM kills

Alert: `SearchMemoryPressure` fires when container memory, `search_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Search is a
supporting-tier service owned by the discovery team; it calls
inventory, redis-cache, and
api-gateway call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Large payloads.** A few very large requests allocate far more than usual.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Memory leak in a recent release.** A new code path keeps references to finished requests.

The most common cause on search is large payloads: it explained 11 of the
last 19 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `search-overview` dashboard and compare `search_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history search --since 2h`. A deploy in the last hour makes
   "large payloads" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n discovery logs deploy/search --since 15m | grep SEA-MEM-211
   ```

4. If `search_rss_pct_of_limit` stays above 94 for 5 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/search`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `cache_max_entries=7` on
   search (`configctl set search cache_max_entries 7`) and restart one pod at a
   time.

## Escalation

Page the discovery secondary after 20 minutes without improvement, or at once if more than
25% of search requests are failing. Coordinate in `#discovery-oncall`.
