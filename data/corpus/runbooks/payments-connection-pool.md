---
service: payments
updated_at: 2025-12-01
---
# Payments: connection pool exhaustion

Alert: `PaymentsPoolExhausted` fires when the time requests wait for a database connection, `payments_pool_wait_ms`, stays above its threshold for 3 minutes. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Connection leak.** A code path that forgets to return connections after an error.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.

The most common cause on payments is connection leak: it explained 17 of the
last 23 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "connection leak" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-POOL-301
   ```

4. If `payments_pool_wait_ms` stays above 382 for 12 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `paymentsctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/payments --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on card-auth.
3. If that doesn't help within 10 minutes, set `pool_checkout_timeout_ms=150` on
   payments (`configctl set payments pool_checkout_timeout_ms 150`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 15 minutes without improvement, or at once if more than
5% of payments requests are failing. Coordinate in `#payments-oncall`.
