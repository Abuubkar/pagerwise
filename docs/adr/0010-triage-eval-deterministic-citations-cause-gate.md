---
status: accepted
date: 2026-11-03
supersedes: ADR 0009's "v1 column is kept until 6b"; 6b's planned LLM judge for citations
---

# Triage eval: deterministic citation checks, a cause decision line, v1 embeddings dropped

**Citations are checked in code, not by a judge model.** The plan was a local judge gated at Cohen's kappa ≥ 0.70
against hand labels (`evals/golden/calibration.csv`: 40 tune rows, 26 yes / 14 no, to develop on; 20 held-out
rows, 12 / 8, to confirm on; every label reviewed by hand). No local judge got there:

| Judge | Prompt | Tune kappa | Held-out kappa |
|---|---|---|---|
| llama3.1:8b | judge/1 (yes/no) | 0.371 | — |
| llama3.1:8b | judge/2 (per-fact statuses, rule in code) | −0.02 | — |
| gemma4:12b | judge/2 | 0.60 | — |
| gemma4:12b | judge/3 | 0.55 | — |
| gemma4:12b | judge/4 | 0.61 | 0.26 |

Tuning stopped at judge/4: tune kappa had plateaued and the held-out drop showed the prompt fitting the tune rows.
`triage_eval.check_citations` replaces it. A (sentence, cited source) pair passes when every specific token of the
sentence (numbers, versions, deploy and error ids, identifiers, backticked text, timestamps, service names), less
what the incident itself gives, appears in one of the sentence's cited sources, and this source holds at least one;
it fails if the source is a deploy from after the incident opened, or a postmortem whose content a cause or impact
sentence states without framing it as past. A sentence with no specific tokens isn't checked (about 22%). Against
the same labels it agrees 0.77 on tune (kappa 0.47) and **0.81 on held-out (kappa 0.61)**, about what the best judge
did on tune, with no model, in milliseconds and identical on every run. It errs toward passing (a fail is nearly
always right), so citation precision is an upper bound. Its agreement is measured on the briefs the labels were
drawn from (`CALIBRATION_BRIEFS`), so it describes the check, not a run. The judge stays runnable (`--judge-model`)
and ungated.

**Deploy evidence ends when the incident opened, and says how long before it each deploy was.** The triage/4 briefs
cited 5 deploys from after the incident started as candidate causes: the evidence window ran 15 minutes past the
open time, and a 9B model misreads ISO timestamps. Each deploy item now ends "It was N minutes before the incident
opened." The golden deploys also gave the answer away (author "Golden Set", summaries naming the failure); they now
look like any other release.

**The cause decision is a line, applied in code (triage/6).** With every rule in prose (triage/5), the model wrote
`INSUFFICIENT_EVIDENCE` on 6 of 30 unanswerable briefs; 12 explained in prose that nothing matched (still stored as
CAUSE_IDENTIFIED) and 12 blamed a nearby deploy. Small models abstain when evidence is missing but not when it is
plausible and wrong (runbooks for other failures, a deploy minutes before), even with a constrained decision field
([arXiv 2608.22228](https://arxiv.org/html/2608.22228)); that paper's conclusion is that it takes a signal from
outside the model. Here: Likely cause opens with `Match: [Cn]` or `Match: none`. `citations.LikelyCauseGate` drops
the line and, unless it names a runbook or postmortem, makes the section exactly `INSUFFICIENT_EVIDENCE`: a deploy
alone is never a cause, by the item's source type, not the model's judgment. The decision comes first, so the
stream never shows a cause it then takes back; text outside that line streams as before. A Likely cause without the
line is a broken contract (`format_invalid`). `triage_runs.raw_text` keeps what the model wrote, line included; the
stream, the parsed brief and a replay all go through the gate. A separate classifier call first (the "sufficient
context" rater approach) was the alternative: same 9B model, same weakness, 3–5 s more time to first token.

**Results** (41 dev cases × 3, qwen3.5:9b-q4_K_M; triage/6 is the full live run replayed through the fixed gate,
see below; gates set before these runs and not moved):

| Metric | triage/4 | triage/5 | triage/6 dev | triage/6 test | Gate |
|---|---|---|---|---|---|
| Root cause hit@1 | 0.760 | 0.840 | 0.800 | 0.600 | ≥ 0.60 |
| Root cause hit@3 | 0.920 | 0.920 | 0.840 | 0.667 ✗ | ≥ 0.80 |
| Abstention | 0.000 | 0.100 | 0.400 ✗ | 0.200 ✗ | ≥ 0.80 |
| Degraded honesty | 1.000 | 1.000 | 1.000 | 1.000 | 1.0 |
| Format validity | 0.976 | 0.976 | 0.927 ✗ | 0.750 ✗ | ≥ 0.95 |
| TTFT p95 | 18.8 s | 20.1 s ✗ | 20.4 s ✗ | 20.8 s ✗ | ≤ 20 s |
| Total p95 | — | 43.7 s | 42.3 s | 40.5 s | ≤ 45 s |
| Citation precision | 0.951 | 0.946 | 0.962 | 0.962 | ≥ 0.90 |
| Unsupported-claim rate | 0.090 ✗ | 0.046 | 0.158 ✗ | 0.121 ✗ | ≤ 0.08 |
| Deploy citations after start | 5 | 0 | 0 | 0 | — |

Results: `evals/results/20261103T013618-dev-v2.json` (triage/5), `20261103T033924-dev-v2.json` (triage/6 live),
`20261103T045037-dev-v2.json` (triage/6 replayed after the gate fix: same model outputs, 3 empty sections recovered).
Test split: 24 held-out cases × 3, `evals/results/20261103T082021-test-v2.json`, run once to confirm. Its TTFT
p50 (1.2 s) is not a real number: Ollama reused the cached prompt for repeats 2 and 3 of 22 of the 24 cases (the
41-case dev runs cycle through more prompts than the cache holds, so they never hit it). The first repeats alone
give p95 ≈ 21.8 s; the gate is missed either way. Outputs are identical across repeats (temperature 0), so quality
metrics are unaffected.

The first live run of triage/6 showed a gate bug: when the model wrote the cause on the decision line
(`Match: [C1] The pool…`) the gate dropped the whole line. It now keeps what follows the tags.

**triage/6 is kept, missing four gates.** It quadruples abstention but costs citation discipline: 13 uncited cause or
impact sentences in the first repeat against triage/5's 3, many of them about the rule itself. triage/5 misses two
gates, but names a cause for 9 in 10 incidents the evidence can't explain, and a wrong cause reads exactly like a
right one; a missing tag is visible in the UI. The remaining abstention misses are the model matching a runbook for a
different failure on the same service. Prompt wording has been taken as far as it goes on this model; closing these
gates needs a larger model, faster hardware for TTFT, or a deterministic rule for uncited sentences, each its own
decision.

**TTFT gate raised from 10 s to 20 s.** On this Mac the 9B model takes 16–19 s to read a 3,100–3,900-token triage
prompt before its first token; no prompt change gets that under 10 s. The 20 s gate was set from one 18.8 s run,
without headroom over run-to-run variance; triage/5 and triage/6 both miss it by under half a second. It stays at
20 s: the miss is reported, not absorbed.

**chunks.embedding (v1) dropped**, as ADR 0009 planned once triage passed on v2: migration 0010 makes it nullable
(code that stops writing it can deploy first), 0011 drops its HNSW index `CONCURRENTLY` and then the column;
docs/migrations.md has the rollback. Retrieval and clustering metrics were unchanged after the drop. The column
keeps its name `embedding_v2`: renaming it buys nothing and costs another two-step migration. Incidents still use
bge-small (384-d).

**Known weaknesses.**
- The deterministic check sees tokens, not meaning: a sentence with the right numbers and a wrong claim passes.
- The calibration labels come from one person and one generator (triage/4 briefs).
- The gate trusts the model's choice among runbooks and postmortems; it only stops a cause with none. Matching a
  runbook for a different failure is the main abstention miss.
- Four gates are missed on dev (abstention, format validity, TTFT p95, unsupported-claim rate), five on test (hit@3
  too); see Results.
- triage/6 sometimes copies a rule into Blast radius ("The whole section is exactly INSUFFICIENT_EVIDENCE."): 6 of
  123 dev briefs, 9 of 72 test briefs, none with triage/5. It's half the test format failures.
- Repeats of a case can hit Ollama's prompt cache when the split has few enough cases, which makes TTFT p50 and
  tokens/s meaningless for that run.
