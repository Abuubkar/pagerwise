---
service: postgres-primary
updated_at: 2026-09-18
---
# Postgres primary: dependency timeouts

Alert: `PostgresPrimaryUpstreamTimeouts` fires when the share of calls to a dependency that time out, `postgres_primary_upstream_timeout_pct`, stays above its threshold for 5 minutes. Postgres primary is a
data-tier service owned by the platform team; it calls
no other internal services, and
auth, inventory, ledger, orders call it.

## Symptoms

- Timeouts concentrate on calls to its database.
- The service's own CPU and memory look normal.
- Thread or connection pools fill while waiting.

## Likely causes

- **Timeout set too low.** A recent config change shortened the timeout below normal latency.
- **Network path.** Packet loss between zones adds retransmits.
- **Dependency degraded.** its database itself is slow or partially down.

The most common cause on postgres-primary is timeout set too low: it explained 16 of the
last 17 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `postgres-primary-overview` dashboard and compare `postgres_primary_upstream_timeout_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history postgres-primary --since 2h`. A deploy in the last hour makes
   "timeout set too low" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n platform logs deploy/postgres-primary --since 15m | grep POS-DEP-575
   ```

4. If `postgres_primary_upstream_timeout_pct` stays above 5 for 7 minutes, treat it as
   dependency timeouts and move to mitigation; below that it usually recovers on its own.
5. Check its database's own dashboard before changing anything in postgres-primary.

## Mitigation

1. Open the circuit breaker for its database if the feature can degrade.
2. Fail over calls to the standby region for its database if one exists.
3. If that doesn't help within 10 minutes, set `circuit_breaker_threshold=31` on
   postgres-primary (`configctl set postgres-primary circuit_breaker_threshold 31`) and restart one pod at a
   time.

## Escalation

Page the platform secondary after 15 minutes without improvement, or at once if more than
20% of postgres-primary requests are failing. Coordinate in `#platform-oncall`.
