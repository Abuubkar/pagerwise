---
status: accepted
date: 2026-11-02
---

# Chunks sized by the embedding tokenizer; answers checked against a strict [Cn] citation contract

**Chunking** (`chunking.py`): split on markdown headings, then merge neighbours to 300–500 tokens, counted with
the embedding model's own tokenizer (`fastembed`'s `TextEmbedding.token_count`) on exactly the text that gets
embedded (heading path + chunk). A merged chunk's heading path is the common ancestor of its sections. A heading
with no text of its own is carried into the next section. Code blocks are never split; one that alone exceeds
500 tokens is an error, not a silent split.

**Citations** (`citations.py`): each retrieved chunk goes into the prompt as `[C1]`…`[C8]`. The parser accepts
only exact `[Cn]` tags that were supplied. Verdicts:
- `ANSWERED`: at least one tag, all supplied.
- `INSUFFICIENT_EVIDENCE`: the token appears anywhere. An abstention names no cause, whatever else it says.
- `REJECTED`: an unknown tag, a malformed one (`[C1, C2]`), or no tags at all. The answer is still stored and
  returned with its `problems`, so failures can be inspected and counted.

## Considered options

- **Counting tokens with a word or character heuristic**: no model load, but bge-small silently drops anything
  past 512 tokens, so a heuristic that undercounts loses text from the embedding with no error.
- **The chat model's tokenizer**: Ollama has no tokenizer endpoint. The embedding count is a stand-in for the
  prompt budget too, with a 10% margin.
- **Accepting grouped tags** (`[C1, C2]`): friendlier to the model, but two tag syntaxes to parse and later to
  stream-scan (slice 2). The prompt shows `[C2][C5]` instead.
- **Structured output (JSON) for the answer**: would make the verdict a field, but the answer streams to the UI as
  text from slice 2 on; a JSON envelope can't be shown until it's complete.

## Assumptions

- Runbooks are short, so most become one or two chunks. With 6 runbooks and top-8 retrieval, every question sees
  the whole corpus; retrieval quality is first measured in slice 4 with 180 documents.
- The bge tokenizer counts within ~10% of Qwen's on English runbook text. Measured in slice 1: 3,245 bge tokens
  for question 1's prompt against 3,255 counted by Ollama (0.3%); the budget adds 10% on top.
- fastembed's `token_count` stops at bge's 512-token window, so `count_tokens` counts line by line (exact for
  WordPiece, which has no line-break token). A single line over 512 tokens would still be undercounted.
