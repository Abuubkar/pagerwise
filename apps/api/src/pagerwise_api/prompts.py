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


def _evidence(evidence: list[EvidenceChunk]) -> str:
    return "\n\n".join(f"[{c.tag}] ({c.source}: {c.heading_path})\n{c.text}" for c in evidence)


def ask_messages(question: str, evidence: list[EvidenceChunk]) -> list[dict[str, str]]:
    blocks = _evidence(evidence)
    return [
        {"role": "system", "content": ASK_SYSTEM},
        {"role": "user", "content": f"Evidence:\n\n{blocks}\n\nQuestion: {question}"},
    ]


TRIAGE_PROMPT_VERSION = "triage/2"

TRIAGE_SYSTEM = """\
You write the first triage brief for an incident, for the on-call engineer. Use only the evidence chunks below. \
Each chunk starts with a tag such as [C1]. The incident description after the evidence is what you are triaging; \
it is not evidence and not a past incident.

Write exactly these four sections, in this order, each starting with its heading line, and nothing before the first:

## Likely cause
## Blast radius
## First steps
## Similar incidents

Rules:
1. End every sentence that states a fact with the tag of the chunk that supports it, for example: \
"Payments p99 rises when the ledger pool drops below 20 idle connections [C2]." If two chunks support it, write \
both tags: [C2][C5].
2. Only use tags that appear in the evidence. Never make up a tag. Do not use knowledge from outside the chunks.
3. Likely cause: the most likely cause and why, in at most 3 sentences. If the evidence does not point to a cause, \
the whole section is exactly INSUFFICIENT_EVIDENCE.
4. Blast radius: which services and users are affected, per the evidence. If the evidence says nothing about it, \
the whole section is exactly INSUFFICIENT_EVIDENCE.
5. First steps: a numbered list of at most 5 steps from the evidence, each ending with its tag. Include the exact \
commands from the chunks. If there are none, the whole section is exactly INSUFFICIENT_EVIDENCE.
6. Similar incidents: past incidents that a chunk describes (a postmortem or an incident write-up), with tags. A \
runbook's instructions are not a past incident. If no chunk describes a past incident, the whole section is \
exactly: None in the evidence."""


def triage_messages(incident: str, evidence: list[EvidenceChunk]) -> list[dict[str, str]]:
    blocks = _evidence(evidence)
    return [
        {"role": "system", "content": TRIAGE_SYSTEM},
        {"role": "user", "content": f"Evidence:\n\n{blocks}\n\nIncident:\n{incident}"},
    ]
