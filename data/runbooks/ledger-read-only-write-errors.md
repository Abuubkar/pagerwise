---
service: ledger
---
# Ledger: writes fail with read-only transaction errors

Alert: `LedgerWriteErrors` fires when more than 1% of ledger writes fail over 5 minutes.

## What the error means

When ledger writes fail with `cannot execute INSERT in a read-only transaction` (SQLSTATE 25006), ledger is still
connected to a Postgres server that is no longer the primary. This almost always follows a postgres-primary
failover or switchover: the old primary was demoted to a replica, but connections opened before the failover still
point at it.

Ledger pods hold pooled connections for up to 10 minutes (`max_lifetime = 600s`). Without action, write errors
continue until every stale connection has been replaced, which can take the full 10 minutes.

## Diagnosis

Confirm the error code in the ledger logs:

```bash
kubectl -n ledger logs deploy/ledger --since=10m | grep -c 25006
```

Then confirm that a failover happened. The postgres-primary runbook "Postgres primary: failover and switchover"
explains how to see the current leader.

## First steps

1. Confirm the failover has finished and a new primary is accepting writes (see the postgres-primary runbook).
2. Recycle the ledger connection pools so every pod reconnects to the new primary right away:

```bash
kubectl -n ledger exec deploy/ledger -- ledgerctl pool recycle --all-pods
```

3. Watch the write error rate. It should drop to zero within one minute of the recycle.
4. Do not restart ledger pods instead of recycling. A rolling restart takes about 6 minutes for 6 pods and drops
   in-flight requests.

## Escalation

If errors continue after a recycle, the new primary may itself be read-only. Page the database on-call.
