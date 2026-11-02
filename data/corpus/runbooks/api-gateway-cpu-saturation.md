---
service: api-gateway
updated_at: 2026-01-05
---
# Api gateway: CPU saturation

Alert: `ApiGatewayCPUSaturated` fires when CPU utilisation, `api_gateway_cpu_util_pct`, stays above its threshold for 10 minutes. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Traffic spike.** Legitimate load above what the current replica count serves.
- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Hot loop in a release.** A recent change made a common path far more expensive.

The most common cause on api-gateway is traffic spike: it explained 19 of the
last 22 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "traffic spike" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-CPU-608
   ```

4. If `api_gateway_cpu_util_pct` stays above 94 for 6 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `cache_ttl_s=36` on
   api-gateway (`configctl set api-gateway cache_ttl_s 36`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 30 minutes without improvement, or at once if more than
20% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
