---
service: notifications
updated_at: 2025-12-04
---
# Notifications: connection pool exhaustion

Alert: `NotificationsPoolExhausted` fires when the time requests wait for a database connection, `notifications_pool_wait_ms`, stays above its threshold for 3 minutes. Notifications is a
supporting-tier service owned by the growth team; it calls
kafka-broker, and
orders call it.

## Symptoms

- Pool `waiting` count is above zero for minutes, not seconds.
- Database CPU is normal: the queue is in the application, not the database.
- Latency rises before errors do.

## Likely causes

- **Pool too small for the replica count.** Fewer pods than usual means each pod's pool takes more load.
- **Long transactions holding connections.** A slow code path keeps connections checked out.
- **Connection leak.** A code path that forgets to return connections after an error.

The most common cause on notifications is pool too small for the replica count: it explained 29 of the
last 30 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `notifications-overview` dashboard and compare `notifications_pool_wait_ms` with the
   same hour last week.
2. Check recent changes: `deployctl history notifications --since 2h`. A deploy in the last hour makes
   "pool too small for the replica count" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n growth logs deploy/notifications --since 15m | grep NOT-POOL-255
   ```

4. If `notifications_pool_wait_ms` stays above 379 for 5 minutes, treat it as
   connection pool exhaustion and move to mitigation; below that it usually recovers on its own.
5. Run `notificationsctl pool stats` on two pods; idle near zero on both confirms exhaustion.

## Mitigation

1. Scale out: `kubectl -n platform scale deploy/notifications --replicas=+2` (each pod brings its own pool).
2. Kill transactions open for more than 60 s with `pg_terminate_backend` on kafka-broker.
3. If that doesn't help within 10 minutes, set `statement_timeout_ms=640` on
   notifications (`configctl set notifications statement_timeout_ms 640`) and restart one pod at a
   time.

## Escalation

Page the growth secondary after 45 minutes without improvement, or at once if more than
5% of notifications requests are failing. Coordinate in `#growth-oncall`.
