---
service: ledger
---
# Ledger: connection pool exhaustion

Alert: `LedgerPoolIdleLow` fires when idle database connections in any ledger pod stay below 20 for 3 minutes.

## How the pool is sized

Each ledger pod keeps a pool of at most 40 connections to postgres-primary. There are 6 ledger pods, so ledger can
hold up to 240 connections. postgres-primary has `max_connections = 300`, and the remaining 60 are reserved for
migrations, replication and humans.

A connection is returned to the pool when its transaction ends. Long transactions are the usual reason the pool
drains: a single report query holding a connection for minutes takes it out of rotation for everyone.

## Diagnosis

### Check the pool

```bash
kubectl -n ledger exec deploy/ledger -- ledgerctl pool stats
# idle=8 in_use=32 waiting=17 max=40
```

`waiting` above 0 means requests are queueing for a connection. Queueing over 2 seconds shows up as payments
latency, because payments writes a ledger entry on every charge.

### Find long transactions

```sql
SELECT pid, now() - xact_start AS age, state, left(query, 80) AS query
FROM pg_stat_activity
WHERE usename = 'ledger' AND xact_start IS NOT NULL
ORDER BY age DESC
LIMIT 10;
```

Anything older than 30 seconds is suspect. The nightly reconciliation job runs at 02:00 UTC and is the most common
offender when it overlaps with peak traffic in APAC.

## First steps

1. Run `ledgerctl pool stats` on two or three pods to confirm the pool is low everywhere, not on one pod.
2. Find long transactions with the query above. Cancel a reconciliation query with `SELECT pg_cancel_backend(pid)`;
   it is safe to cancel and resumes from its last checkpoint.
3. Do not raise the pool size above 40. Six pods at 50 would need 300 connections, which is all of postgres-primary.
4. If the pool stays low with no long transactions, check postgres-primary itself for lock waits or replication
   problems.

## Escalation

Page the database on-call if pool exhaustion lasts over 15 minutes with no long transaction to cancel.
