---
status: accepted
date: 2026-11-02
---

# Kafka ingestion: Redpanda, aiokafka, non-blocking retry topics, offsets committed after the database

**Broker and client.** Redpanda v26.2.6 (Kafka API, one node in compose, `--mode dev-container`, topic
auto-creation off) and aiokafka 0.15.0. Topics are created by `pagerwise_kafka.create_topics`, which the topics
script and the service tests share; `alerts.v1`, `alerts.retry.30s` and `alerts.retry.5m` have 12 partitions keyed
by service, `alerts.dlq` has one so a DLQ offset range means one thing. The alert payload is
`contracts/kafka/alert.v1.json` (JSON Schema); `make codegen` generates the Pydantic model with
datamodel-code-generator 0.87.0. `contracts/kafka/asyncapi.yaml` (AsyncAPI 3.1.0, the current release; the plan
said 3.0) documents channels, keys, headers and the consumer group.

**Delivery: at-least-once plus idempotent writes.** Auto-commit is off. Each partition has an `OffsetTracker`; a
record is marked done only after its row is committed in Postgres (or after it has been republished to a retry
topic or the DLQ), and the consumer commits each partition's first unfinished offset once a second. Rows are
`INSERT ... ON CONFLICT (event_id) DO NOTHING`, so a redelivered record inserts nothing and is counted as a
duplicate. Dead letters are unique on their original topic/partition/offset, which survive every retry hop in
headers (`x-original-*`), so a re-dead-lettered message is still one row.

**Ordering and parallelism.** One worker task per assigned partition processes that partition's records in
order, in batches of up to 500 rows per INSERT; partitions run in parallel. Producers use `acks=all` with
idempotence.

**Retries don't block.** A transient failure republishes the message to `alerts.retry.30s`, then
`alerts.retry.5m` (x-attempt 1, 2), and commits the original offset; the third failure, or any permanent one
(a payload that fails AlertV1), goes to `alerts.dlq` and `dead_letters`. A retry topic's record isn't processed
before its publish time plus the topic's delay: the poll loop seeks back to it and pauses the partition until it's
due, so not-yet-due messages wait in Kafka, not in memory, and don't count against backpressure. If Postgres or
Kafka itself fails, the batch is retried in place with backoff instead: that failure isn't the message's, and
routing every message to a retry topic during an outage would only move the outage.

**Backpressure.** Fetching pauses for every assigned partition when 500 records are queued or 90% of the consumer's
20-connection pool is checked out, and resumes at 100 queued and 50% (`flow.Backpressure`; the gap is the
hysteresis). Pausing doesn't leave the group: aiokafka heartbeats in the background and `getmany()` keeps being
called.

**Assignment: round-robin, not sticky.** aiokafka offers range, round-robin and sticky assignors, none
cooperative, so every rebalance revokes everything. The first version used sticky, hoping to keep partitions
where they were. The rebalance service test failed intermittently: sticky balances the *total* across the three
subscribed topics, so a second replica sometimes got 12 retry.30s + 6 retry.5m partitions and none of
`alerts.v1`, meaning a new replica added no ingest capacity. Round-robin deals each topic out evenly when every
member subscribes to the same topics.

**Rebalance and shutdown.** On revoke, queued-but-unstarted records are dropped (the next owner re-reads them
from the last commit), in-flight batches finish (up to 20 s), and finished offsets are committed. On SIGTERM the
consumer stops polling, drains its queues for up to 20 s, commits and exits; aiokafka doesn't call the revoke
listener on `stop()`, so that commit is ours.

**DLQ replay** is `POST /v1/admin/dlq/replay` with a DLQ offset range or message keys. It reads `dead_letters`
(not the topic), republishes each payload to `alerts.v1` with `x-replayed-from`, and marks the rows replayed.

**Alternatives considered.**
- *confluent-kafka-python* (librdkafka; faster, has cooperative rebalancing): its asyncio support is newer and
  thinner, and the plan names aiokafka. Revisit if one consumer can't keep up.
- *Blocking retries* (sleep and retry in the partition): simple, but one bad message stalls every alert behind it.
- *A separate consumer group per retry topic*: isolates retry lag from ingest, at the cost of more processes;
  not needed while one group keeps up.
- *Writing dead letters from a separate DLQ consumer*: one more process; the consumer already has the error.

**Assumptions.**
- One consumer replica sustains 2,000 alerts/s on this laptop: in the storm the survivor ran alone for the last
  two minutes and ended with alerts.v1 lag at 293 (docs/runs/slice-03-done-when.txt).
- A dead replica is noticed after the group session timeout (aiokafka's default 10 s); its partitions stall that
  long. In the storm that pushed alerts.v1 lag to 21k and ingest freshness p95 to 6.3 s, over the 5 s target.
  A shorter session timeout trades that for more false rebalances on a slow GC or a busy laptop.
- Retry delays are measured from the retry message's publish time, which assumes broker and consumer clocks
  roughly agree.
- `event_id` is unique per alert; a producer that reuses one loses the second alert silently (counted as a
  duplicate).
- The 5% transient failures in the storm are injected (`CONSUMER_FAULT_TRANSIENT_RATE`, picked by a hash of
  event_id so replicas agree); nothing real fails transiently per message yet.
