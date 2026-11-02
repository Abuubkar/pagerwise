---
service: api-gateway
updated_at: 2026-02-23
---
# Api gateway: dependency timeouts

Alert: `ApiGatewayUpstreamTimeouts` fires when the share of calls to a dependency that time out, `api_gateway_upstream_timeout_pct`, stays above its threshold for 5 minutes. Api gateway is a
edge-tier service owned by the platform team; it calls
auth, payments, orders, search.

## Symptoms

- Timeouts concentrate on calls to auth.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Network path.** Packet loss between zones adds retransmits.
- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Dependency degraded.** auth itself is slow or partially down.

The most common cause on api-gateway is network path: it explained 10 of the
last 12 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `api-gateway-overview` dashboard and compare `api_gateway_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history api-gateway --since 2h`. A deploy in the last hour makes
   "network path" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/api-gateway --since 15m | grep API-DEP-220
   ```

4. If `api_gateway_upstream_timeout_pct` stays above 10 for 4 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check auth's own dashboard before changing anything in api-gateway.

## Mitigation

1. Open the circuit breaker for auth if the feature can degrade.
2. Fail over calls to the standby region for auth if one exists.
3. If that doesn't help within 10 minutes, set `retry_max_attempts=28` on
   api-gateway (`configctl set api-gateway retry_max_attempts 28`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 15 minutes without improvement, or at once if more than
5% of api-gateway requests are failing. Coordinate in `#platform-oncall`.
