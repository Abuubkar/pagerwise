"""Every prompt the app sends. Any wording change bumps its version; answers store the version they used."""

from dataclasses import dataclass

ASK_PROMPT_VERSION = "ask/1"

ASK_SYSTEM = """\
You help on-call engineers during incidents. Answer the question using only the evidence chunks below. Each chunk \
starts with a tag such as [C1].

Rules:
1. End every sentence that states a fact with the tag of the chunk that supports it, for example: \
"Each ledger pod keeps at most 40 connections [C2]." If two chunks support it, write both tags: [C2][C5].
2. Only use tags that appear in the evidence. Never make up a tag.
3. Do not use any knowledge from outside the chunks. If the chunks do not answer the question, reply with exactly \
INSUFFICIENT_EVIDENCE and nothing else.
4. Be brief: at most 6 sentences of plain text, no headings or lists. Include commands from the chunks when they \
are the next step."""


@dataclass
class EvidenceChunk:
    tag: str  # "C1"
    source: str  # "runbook payments-high-p99-latency.md"
    heading_path: str
    text: str


def ask_messages(question: str, evidence: list[EvidenceChunk]) -> list[dict[str, str]]:
    blocks = "\n\n".join(f"[{c.tag}] ({c.source}: {c.heading_path})\n{c.text}" for c in evidence)
    return [
        {"role": "system", "content": ASK_SYSTEM},
        {"role": "user", "content": f"Evidence:\n\n{blocks}\n\nQuestion: {question}"},
    ]
