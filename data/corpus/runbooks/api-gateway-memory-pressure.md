---
service: api-gateway
updated_at: 2026-09-12
---
# Api gateway: memory pressure and OOM kills

Alert: `ApiGatewayMemoryPressure` fires when container memory, `api_gateway_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.
- **Large payloads.** A few very large requests allocate far more than usual.

The most common cause on api-gateway is memory leak in a recent release: it explained 18 of the
last 19 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "memory leak in a recent release" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-MEM-205
   ```

4. If `api_gateway_rss_pct_of_limit` stays above 97 for 5 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/api-gateway`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `gc_target_pct=38` on
   api-gateway (`configctl set api-gateway gc_target_pct 38`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 15 minutes without improvement, or at once if more than
5% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
