# Challenges and how we handled them

What went wrong or got in the way while building Pagerwise, slice by slice: what happened, what we did, why, and
what else we could have done. ADRs record the choices; this file records the bumps that led to some of them.

## Slice 1: walking skeleton

**fastembed's `token_count` caps at 512.** It counts the tokens the model would see, so it never returns more
than bge-small's 512-token window. Chunk sizing was unaffected (anything over 500 still read as too big), but the
prompt-budget guard estimated 680 tokens for a 3,255-token prompt and would never have fired.
- *Did:* `count_tokens` counts line by line and sums (exact for WordPiece; within 0.3% of Ollama's count on a real
  prompt). Found by measuring the estimate before writing it into ADR 0003, not by a test.
- *Alternatives:* reach into fastembed's internal tokenizer and turn truncation off (private attribute, breaks
  on upgrade); add `tokenizers` as a direct dependency (a second way to load the same tokenizer).

**Bare headings became their own chunks.** "## Likely causes" directly above "### Ledger pool" made a two-word
piece that merged upward and moved the whole chunk's heading path to the document title.
- *Did:* a heading with no text of its own is carried into the next section.

**Small tail sections.** Each runbook's short "Escalation" section became a 47-token chunk, because merging only
looked forward from a small chunk.
- *Did:* a piece merges into the previous chunk when either side is under 300 tokens and the result fits in 500.
  One tail (49 tokens) still stands alone where the merge would reach 515.

**Prompt evaluation, not generation, is the slow part.** qwen3.5:9b evaluates ~213 prompt tokens/s on the M1 Pro:
15.3 s of a 24 s answer for a 3,250-token prompt. The plan's TTFT target (≤ 10 s on ~7k tokens) won't hold
as written; recorded as an at-risk assumption in ADR 0001 for slices 5–6.

**Six runbooks are one retrieval window.** They make 8 chunks, and top-8 retrieval returns all of them, so slice 1
tests grounding and abstention, not retrieval. The cosine order is still sensible (the planted fact's chunk ranks
first at distance 0.114; the off-topic question's best match is 0.366). Retrieval is measured from slice 4.
