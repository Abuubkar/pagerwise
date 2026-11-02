---
service: api-gateway
updated_at: 2026-01-06
---
# Api gateway: high p99 latency

Alert: `ApiGatewayLatencyHigh` fires when the p99 of `api_gateway_p99_latency_ms` stays above its threshold for 5 minutes. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- p99 rises first; p50 usually stays flat until the problem spreads.
- Time spent waiting on auth grows faster than time spent in the service itself.
- Request rate is normal: this is slowness, not extra load.

## Likely causes

- **Lock contention.** Long-held row or mutex locks serialize requests under normal load.
- **Garbage collection pauses.** Heap close to its limit makes collection pauses show up in p99.
- **Slow dependency.** Most latency is spent waiting on auth; check its own latency first.

The most common cause on api-gateway is lock contention: it explained 10 of the
last 19 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_p99_latency_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "lock contention" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-LAT-504
   ```

4. If `api_gateway_p99_latency_ms` stays above 1263 for 5 minutes, treat it as
   high p99 latency and move to mitigation; below that it usually recovers on its own.
5. Compare the service's own processing time with the time spent waiting on auth.

## Mitigation

1. Shed non-critical traffic with `trafficctl shed api-gateway --class batch`.
2. If one dependency explains the latency, follow that dependency's runbook.
3. If that doesn't help within 10 minutes, set `query_timeout_ms=50` on
   api-gateway (`configctl set api-gateway query_timeout_ms 50`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 20 minutes without improvement, or at once if more than
5% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
