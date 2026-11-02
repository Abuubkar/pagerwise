---
service: postgres-primary
---
# Postgres primary: failover and switchover

postgres-primary is a 3-node Patroni cluster. Patroni promotes a replica automatically when the leader stops
renewing its lock for 30 seconds (`ttl = 30`). A switchover is the planned version of the same thing.

## Check the cluster state

```bash
kubectl -n postgres exec postgres-primary-0 -- patronictl list
```

The `Leader` row is the current primary. A node in `running` state with role `Replica` is a healthy standby.
After a failover, confirm that the new leader accepts writes:

```sql
SELECT pg_is_in_recovery();  -- false on the primary
```

## What clients see during a failover

- Writes fail for 30–45 seconds while Patroni detects the failure and promotes a replica.
- The `postgres-primary-rw` service follows the leader, but existing connections stay attached to the old node.
  After the old leader is demoted, those connections can still read but every write fails as read-only.
- Clients with connection pools must reconnect. Services that cache connections for a long time (ledger keeps them
  up to 10 minutes) keep failing writes until they recycle their pools.

## Planned switchover

```bash
kubectl -n postgres exec postgres-primary-0 -- patronictl switchover --candidate postgres-primary-1 --force
```

Announce a switchover in #db-changes 15 minutes ahead, and run it outside 12:00–14:00 UTC, the payments peak.

## After any failover

1. Confirm the new leader with `patronictl list` and `pg_is_in_recovery()`.
2. Tell the ledger on-call or run the ledger pool recycle yourself; ledger is the main client with long-lived
   connections.
3. Check replication lag on the remaining replicas; the old leader rejoins as a replica once it is healthy.
4. Open a postmortem if the failover was not planned.
