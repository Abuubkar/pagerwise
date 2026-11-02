---
status: accepted
date: 2026-11-02
---

# Alert clustering in the consumer, incident updates on Redis, alert_events partitioned by day online

**Clustering.** The consumer groups alerts into incidents in the same transaction that stores them
(`pagerwise_consumer.clustering`). Rules, in order: the same service and fingerprint in the last 10 minutes goes to
that alert's incident (unless resolved); otherwise the alert's summary embedding (bge-small, the model retrieval
already uses) is compared with incidents active in the last 15 minutes in services one hop away on the service graph,
either direction, and cosine >= 0.86 joins the most similar; otherwise a new incident opens. The rule is a pure
function (`decide`) with table-driven tests; no LLM is involved. Only groups the fingerprint rule can't place are
embedded, so a storm of repeating alerts costs one embedding per new fingerprint. An incident's `version` rises when
a new fingerprint joins it or its severity rises, not on every repeat, because that's when a triage would change.

**Concurrency.** Two consumers can see related alerts at once: neighbouring services are on different partitions,
and a rebalance can split one service's alerts. Each batch takes `pg_advisory_xact_lock` on every service in its
alerts' neighbourhoods, sorted (so overlapping batches lock in the same order), then decides; an incident it joins
is locked `FOR NO KEY UPDATE`. Not plain `FOR UPDATE`: only non-key columns change, and `FOR UPDATE` also blocks the
`FOR KEY SHARE` lock that every alert insert referencing the incident takes. The service test races two transactions
10 times for the same fingerprint and for neighbouring services; without the advisory lock both fail on the first
round with two incidents. Redelivered alerts are filtered out before clustering, so a duplicate never opens an
incident; if two consumers still insert the same alert, the loser's new incident is deleted in the same transaction.

**Redis pub/sub.** After each commit the consumer publishes one JSON message per changed incident to the
`incidents` channel (opened/updated, version, alert count, severity). Best effort: a failed publish is counted and
logged, never retried, and never fails ingestion; a missed update is re-read from Postgres. Slice 5's GraphQL
subscription is the first reader.

**Partitioning alert_events.** Daily range partitions on `occurred_at`, a DEFAULT partition, and
`create_alert_partitions(days_ahead, days_back, parent)`, which the consumer calls hourly to stay a week ahead.
The primary key becomes `(event_id, occurred_at)` (a unique key must include the partition key), and inserts use
`ON CONFLICT DO NOTHING` without a target so the same code works before and after. The change ran online:
migration 0006 (shadow table + mirror trigger), a resumable 50k-row backfill, migration 0007 (one short
transaction: count check, then renames). docs/migrations.md has the procedure and rollback.

**Lock timeouts in the migrations.** 0007 takes `ACCESS EXCLUSIVE` on `alert_events` and its shadow with
`lock_timeout = 2s` and up to 10 retries: it never waits in the lock queue long, because a queued exclusive request
blocks every writer behind it. 0006 is stricter. Its foreign key locks `incidents` and its trigger locks
`alert_events`, and the consumer writes both tables in either order (a new incident is inserted before its alerts; a
joined one is updated after), so no lock order is safe. The first version deadlocked with the consumer in both of
two live runs. Now 0006 does everything slow first, then takes both locks together with `lock_timeout = 500ms` and
retries: shorter than Postgres's 1 s `deadlock_timeout`, so the migration backs off instead of the deadlock detector
killing a writer's transaction. The next run under the same load had no deadlock.

**Alternatives considered.**
- *Clustering in a separate service* reading alert_events: decouples ingest from clustering, but adds a process and
  a second pass over every row; the consumer already has the batch in hand.
- *Fingerprint-only grouping:* merges nothing across instances; every replica of a failing service would page
  separately (6 incidents per rule in the simulator instead of 1).
- *pg_partman* for partition upkeep: an extension the pgvector image doesn't ship; one plpgsql function does it.
- *Swapping with `ALTER TABLE ... ATTACH PARTITION`* of the old table as one big partition: avoids the copy, but
  leaves one partition with a month of data that never prunes, and its constraint check scans the whole table.
- *SERIALIZABLE transactions instead of advisory locks:* correct, but under a storm many batches would fail and
  retry; the locks serialize only batches whose neighbourhoods overlap.

**Assumptions.**
- One consumer replica keeps up with 2,000 alerts/s with clustering on, but with less headroom than slice 3: lag
  peaked at 3,398 (293 without clustering) and fetching paused 227 times; it drained to 0 within 5 s of the storm.
- Similarity 0.86 on bge-small summary embeddings merges a rule's instances ("p99 1840 ms on payments-2" with
  "p99 610 ms on payments-4") and keeps different rules apart; in the simulator it never merged across services.
  Slice 6's clustering eval measures pairwise F1 against gold groupings.
- Nothing updates or deletes alert_events; the mirror trigger handles both anyway (docs/migrations.md).
- `alert_events_old` is kept for rollback and dropped by a later migration.
