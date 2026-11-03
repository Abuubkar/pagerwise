# Service level objectives

Two SLOs, each over a rolling 30 days, with multiwindow burn-rate alerts. The rules are in
[observability/prometheus/rules.yml](../observability/prometheus/rules.yml) (tested by `make obs-check`); what to do
when one fires is in [alerts.md](alerts.md). Dashboards: Grafana → Pagerwise → Stream and Triage (localhost:3000).

| SLO | Objective | Error budget (30 days) |
|---|---|---|
| Ingest freshness | 99% of stored alerts are committed within 5 s of their first publish | 1% of alerts |
| Triage availability | 99.5% of triages end with a brief | 0.5% of triages |

## Ingest freshness

**SLI:** `pagerwise.ingest.freshness`, a histogram the consumer records for every stored alert: the time from the
alert's first publish (its Kafka timestamp on alerts.v1, carried across retries in `x-original-timestamp`) to the
commit of its row. Good events fall in the `le="5"` bucket.

- **Retried alerts count.** A retry waits at least 30 s on alerts.retry.30s, so every transiently failing alert spends
  budget. The 1% budget is the share of alerts that may need a retry in a month. A storm with 5% injected transient
  failures (`make storm`) overspends it on purpose, and the burn alerts fire.
- **Dead-lettered and duplicate alerts don't count.** They're never stored, or were stored the first time. Dead
  letters have their own alert.
- **The clock:** the producer's timestamp against the consumer's clock. On one machine that's exact; across hosts, clock
  skew adds to it.

## Triage availability

**SLI:** `pagerwise.triage.runs`, counted by the worker when a triage ends, by outcome and error code.

| Counts as | Outcome |
|---|---|
| Good | `done`: a brief, whether the verdict is CAUSE_IDENTIFIED or INSUFFICIENT_EVIDENCE |
| Bad | `model_unavailable` (Ollama unreachable), `prompt_too_long` (evidence over the context budget), `triage_failed` (a worker bug) |
| Neither | `format_invalid` |

- **Why format_invalid is excluded:** the brief arrived, but broke the section contract. That's the model's output
  quality, which the triage eval holds to its format-validity gate (≥ 0.95, missed on main at 0.927 on dev; ADR 0010).
  Counting it here would mix a quality miss into availability and spend most of the budget at today's rate.
- **Not measured:** a triage abandoned because its worker died. The worker can't count its own death, and the run is
  failed later as `triage_abandoned` by `service.start_triage`, which records no metric. A crash loop shows as
  missing triages, not as burned budget. Count those failures there if that matters.

## Burn-rate alerts

The burn rate is how fast the budget is being spent: 1 means it lasts exactly 30 days. Following the Google SRE
workbook (chapter 5), an alert needs both a long window, which proves the burn is significant, and a short window
(1/12 of it), which proves it's still happening and lets the alert clear soon after recovery.

| Alert | Long window | Short window | Burn rate | Budget spent when it fires |
|---|---|---|---|---|
| `FreshnessBudgetBurnFast`, `TriageAvailabilityBudgetBurnFast` | 1 h | 5 m | 14.4 | 2% in an hour |
| `FreshnessBudgetBurnSlow`, `TriageAvailabilityBudgetBurnSlow` | 6 h | 30 m | 6 | 5% in 6 hours |

- **Error-ratio thresholds:** 14.4% and 6% for freshness, 7.2% and 3% for availability.
- **Ticket tier not built:** the workbook's third tier (1× over 3 days) isn't implemented; the dashboards show the burn
  rate over 5 m, 1 h and 6 h.
- **No paging route:** there's no Alertmanager, so alerts show in Prometheus (localhost:9090/alerts) and on the
  dashboards.

## Latency targets (alerts, not SLOs)

- **Triage duration:** p95 ≤ 45 s, the triage eval's total-latency gate. Alert `TriageP95Slow`.
- **Freshness:** p95 ≤ 5 s over 10 minutes. Alert `IngestFreshnessP95High`, which catches a slowdown before the
  budget alerts do.
