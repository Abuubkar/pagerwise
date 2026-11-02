---
service: ledger
updated_at: 2025-12-03
---
# Ledger: connection pool exhaustion

Alert: `LedgerPoolExhausted` fires when the time requests wait for a database connection, `ledger_pool_wait_ms`, stays above its threshold for 3 minutes. Ledger is a
core-tier service owned by the ledger team; it calls
postgres-primary, kafka-broker, and
payments call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Connection leak.** A code path that forgets to return connections after an error.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.

The most common cause on ledger is connection leak: it explained 21 of the
last 29 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `ledger-overview` dashboard and compare `ledger_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history ledger --since 2h`. A deploy in the last hour makes
   "connection leak" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n ledger logs deploy/ledger --since 15m | grep LED-POOL-626
   ```

4. If `ledger_pool_wait_ms` stays above 900 for 6 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `ledgerctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/ledger --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on postgres-primary.
3. If that doesn't help within 10 minutes, set `pool_checkout_timeout_ms=170` on
   ledger (`configctl set ledger pool_checkout_timeout_ms 170`) and restart one pod at a
   time.

## Escalation

Page the ledger secondary after 45 minutes without improvement, or at once if more than
25% of ledger requests are failing. Coordinate in `#ledger-oncall`.
