---
status: accepted
date: 2026-11-02
---

# Local LLM: qwen3.5:9b-q4_K_M through Ollama, thinking off, run natively on the host

Answers (and later triage briefs) come from `qwen3.5:9b-q4_K_M` served by Ollama on the developer's Mac, called
through the official `ollama` Python client with `think: false`, `temperature: 0`, an explicit `num_ctx` and a
`num_predict` cap. Model name and options live in `settings.py`.

The job is instruction-following under a strict contract: put a `[Cn]` tag after every factual sentence, use only
supplied tags, and answer with exactly `INSUFFICIENT_EVIDENCE` when the evidence doesn't cover the question. That
is where Qwen3.5 is strongest in its size class.

## Considered options

- **qwen2.5:7b-instruct** (the plan's default): 4.7 GB and about 1.5× faster, but IFEval 71.2 vs 91.5 (vendor
  numbers, `research/small-local-models-2026-11.md`), and in Ledgerline's slice 6c sweep it was the weakest
  on contract-following agent turns (10/15 vs 14/15).
- **gemma4:12b** (Ledgerline's default): best in that sweep, but 7.6 GB and the slowest of the three. Pagerwise
  also needs the eval judge (`llama3.1:8b`, slice 6) to be able to load next to the generator later.
- **Thinking on**: better reasoning on paper, but a long hidden trace before the first token works against the
  time-to-first-token target, and the answer contract needs no reasoning trace.

## Assumptions

- Hardware is an Apple M1 Pro with 16 GB RAM, Ollama 0.x native (Docker on macOS has no GPU access).
- Measured 2026-11-02 on slice 1's three questions (~3,250-token prompts): **~213 prompt tokens/s** and
  ~22 output tokens/s, 5.1 s cold load. Prompt evaluation dominates: 15.3 s of a 24 s answer.
- **At risk:** the plan's triage target is TTFT p95 ≤ 10 s on a ~7k-token prompt. At 213 prompt tok/s that is
  ~33 s. Slice 5/6 must either shrink the prompt, reuse Ollama's prompt cache, or recalibrate the target; if
  qwen2.5:7b turns out much faster on prompt eval with acceptable quality, supersede this ADR with the numbers.
- `think: false` holds up for citation-tagged answers; the slice 6 eval (format validity, citation precision)
  checks it.
