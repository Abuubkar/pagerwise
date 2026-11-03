# Alert runbooks

Every alert in [observability/prometheus/rules.yml](../observability/prometheus/rules.yml) links here. The SLOs behind
the burn-rate alerts are in [slo.md](slo.md).

- **Local endpoints:**
  - Grafana: localhost:3000 (dashboards Pagerwise / Stream and Pagerwise / Triage).
  - Jaeger: localhost:16686.
  - Prometheus: localhost:9090.
- **Sampling:** traces are tail-sampled (observability/collector.yaml). Errors, DLQ hops, retried batches, degraded
  retrieval and slow triages are always kept, and 10% of everything else.

## freshness-budget-burn

`FreshnessBudgetBurnFast` / `FreshnessBudgetBurnSlow`: more than 14.4% (1 h and 5 m) or 6% (6 h and 30 m) of stored
alerts are taking longer than 5 s from publish to commit.

1. **Find where the time goes.** Stream dashboard, *Ingest freshness*: click an exemplar dot on the p95 line to open
   that alert's trace. Its hops show where it waited.
   - A retry hop (alerts.retry.30s) means transient failures.
   - A long gap before `alerts.v1 process` means lag.
   - A slow batch (follow the process span's link) means Postgres.
2. **Retried share:** *Events/s by outcome*. If `retried` is a large share, find the failing dependency from the
   `error.type` on the failed process spans (Jaeger: service pagerwise-consumer, tag `error=true`).
3. **Lag:** if lag is up too, see [consumer-lag-high](#consumer-lag-high).

## triage-availability-budget-burn

`TriageAvailabilityBudgetBurnFast` / `Slow`: triages are failing for system reasons (model_unavailable,
prompt_too_long, triage_failed), not because of the model's format.

1. **Which code:** Triage dashboard, *Triages by outcome*.
2. **model_unavailable:** see [ollama-unreachable](#ollama-unreachable).
3. **prompt_too_long:** evidence grew past the context budget. Check `settings.llm_num_ctx`, and the evidence counts
   (`triage_runbooks_k`, `triage_postmortems_k`, `triage_deploys_max`) against the prompt. Jaeger: the failed `triage` span's `evidence *` children carry result
   counts.
4. **triage_failed:** a worker bug. The worker logs carry the stack trace, and the Loki line links to the trace.

## consumer-lag-high

`ConsumerLagHigh`: a topic's committed offset is more than 10,000 messages behind its end offset for 5 minutes.

1. **Are the consumers running and assigned?** The Stream dashboard's *Consumer lag per partition* shows whether lag
   is on every partition (consumers too slow or down) or a few (a stuck partition worker).
2. **Backpressure:** *Paused partitions by reason*.
   - `db_pool`: Postgres is the bottleneck. Check slow SQL in a batch trace.
   - `queue`: processing can't keep up. Add a replica, up to the partition count of 12.
3. **Stuck partition:** if lag on one partition never moves, its worker may be wedged. Restart that replica: the
   partition is reassigned, and offsets resume from the last commit (writes are idempotent).

## ingest-freshness-p95-high

`IngestFreshnessP95High`: p95 publish-to-commit time over 5 s for 10 minutes. This usually fires before the budget
alerts. Same steps as [freshness-budget-burn](#freshness-budget-burn).

## dead-letters-high

`DeadLettersHigh`: more than 50 alerts went to alerts.dlq in 10 minutes.

1. **Which error class:** Stream dashboard, *Dead letters by error class*.
   - `PermanentError`: the payload is malformed. A producer is sending bad alerts.
   - `TransientError`: an alert failed three times, so a dependency has been failing for over 5 minutes.
2. **Recent rows:** `SELECT error_class, error, original_topic, count(*) FROM dead_letters WHERE created_at > now() -
   interval '1 hour' GROUP BY 1, 2, 3;`.
3. **One message's history:** its trace. Jaeger: service pagerwise-consumer, operation `alerts.dlq send`. The trace
   has every attempt and its error.
4. **Replaying:** there's no replay tool yet. A republished message should set `x-replayed-from` (contracts/kafka).

## insufficient-evidence-rate-high

`InsufficientEvidenceRateHigh`: over the last hour, at least 10 briefs, and the share that abstained
(INSUFFICIENT_EVIDENCE) is more than twice its 7-day average. The model abstains when evidence doesn't support a
cause, so a jump usually means retrieval broke, not that incidents got harder.

1. **Degraded sources:** Triage dashboard, *Degraded evidence sources*. A source timing out is left out of every
   brief.
2. **Empty search:** `curl 'localhost:8001/v1/search?q=connection+pool+exhausted'` should return runbook chunks. If
   it's empty, the corpus import failed or the documents table was emptied; rerun `uv run python -m pagerwise_indexer`.
3. **Retrieval latency:** *Retrieval p95 by stage*. A slow `vector` stage after a migration may mean a missing HNSW
   index.
4. **Recent changes:** a prompt or model change also moves this. Check the latest eval report (evals/REPORT.md).

## triage-p95-slow

`TriageP95Slow`: p95 triage time, from claim to last event, over 45 s for 15 minutes.

1. **Model or evidence:** open a slow triage from an exemplar on *Triage duration*, then compare its `chat` span with
   its `evidence *` spans. Evidence sources are capped by their timeouts (2 s, 2 s, 0.5 s), so the time is almost
   always the model.
2. **Slow chat span:**
   - `pagerwise.ttft_ms` high: prompt processing. Is the prompt bigger (`gen_ai.usage.input_tokens`)? Was the model
     evicted (Ollama `keep_alive`)?
   - `pagerwise.tokens_per_second` low: another process is using the GPU. Check `curl localhost:11434/api/ps`.
3. **Queueing:** a triage waits for the one before it; one worker serves one model.

## ollama-unreachable

`OllamaUnreachable`: the triage worker's probe of Ollama (`GET /api/version`, every 15 s) has failed for 2 minutes.
Triages fail as model_unavailable meanwhile.

1. **Is it running?** `curl localhost:11434/api/version`. Ollama runs natively on the host, not in Docker (ADR 0001).
   Start the app or `ollama serve`.
2. **Right host?** The worker reads `OLLAMA_HOST` (settings.ollama_host).
3. **No data at all:** if the alert never fires but triages fail, the worker itself is down. The gauge disappears
   with it, and this alert can't fire without data.
