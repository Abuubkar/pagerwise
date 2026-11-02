---
service: payments
updated_at: 2026-05-18
---
# Payments: dependency timeouts

Alert: `PaymentsUpstreamTimeouts` fires when the share of calls to a dependency that time out, `payments_upstream_timeout_pct`, stays above its threshold for 5 minutes. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- Timeouts concentrate on calls to card-auth.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Dependency degraded.** card-auth itself is slow or partially down.
- **Network path.** Packet loss between zones adds retransmits.

The most common cause on payments is timeout set too low: it explained 18 of the
last 26 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "timeout set too low" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-DEP-357
   ```

4. If `payments_upstream_timeout_pct` stays above 4 for 3 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check card-auth's own dashboard before changing anything in payments.

## Mitigation

1. Open the circuit breaker for card-auth if the feature can degrade.
2. Fail over calls to the standby region for card-auth if one exists.
3. If that doesn't help within 10 minutes, set `upstream_timeout_ms=200` on
   payments (`configctl set payments upstream_timeout_ms 200`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 45 minutes without improvement, or at once if more than
10% of payments requests are failing. Coordinate in `#payments-oncall`.
