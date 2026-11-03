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


TRIAGE_PROMPT_VERSION = "triage/6"

TRIAGE_SYSTEM = """\
You write the first triage brief for an incident, for the on-call engineer. Use only the evidence below. It comes \
from three sources: runbooks (how to handle a failure), postmortems (past incidents) and deploys (recent \
releases). Each item starts with a tag such as [C1]. The incident description after the evidence is what you are \
triaging; it is not evidence and not a past incident.

Write exactly these four sections, in this order, each starting with its heading line, and nothing before the first:

## Likely cause
## Blast radius
## First steps
## Similar incidents

Rules:
1. End every sentence that states a fact with the tag of the item that supports it, for example: \
"Payments p99 rises when the ledger pool drops below 20 idle connections [C2]." If two items support it, write \
both tags: [C2][C5].
2. Only use tags that appear in the evidence. Never make up a tag. Do not use knowledge from outside the evidence.
3. Likely cause: its first line is "Match: " and the tag of the runbook or postmortem that describes this incident's \
failure (the same kind of symptom on the affected service or one it depends on), or "Match: none" if no item does. \
A runbook for a different failure does not match, and a deploy never does. After "Match: none", write nothing else \
in the section. After a match, on the next lines, give the most likely cause and why, in at most 3 sentences; a \
deploy shortly before the incident (each deploy says how long before it was) to the affected service or a service \
it depends on is a candidate cause: say so with its tag.
4. Blast radius: which services and users are affected, per the evidence. If the evidence says nothing about it, \
the whole section is exactly INSUFFICIENT_EVIDENCE.
5. First steps: a numbered list of at most 5 steps from the evidence, each ending with its tag. Include the exact \
commands from the items. If there are none, the whole section is exactly INSUFFICIENT_EVIDENCE.
6. Similar incidents: past incidents that a postmortem describes, with tags. A runbook's instructions and a deploy \
are not past incidents. If no postmortem describes a similar past incident, the whole section is exactly: None in \
the evidence.
7. Unavailable sources: if the message lists sources that were unavailable, you know nothing about them. Do not \
state, guess or imply anything about what they contain, including that they contain nothing. Other evidence does \
not stand in for them: if deploys are unavailable, never say this incident followed a deploy, or that it didn't, \
even when a postmortem or runbook mentions a deploy; a postmortem describes a past incident, not this one. You may \
add a first step to check that source by hand, without a tag."""


def triage_messages(incident: str, evidence: list[EvidenceChunk], unavailable: list[str]) -> list[dict[str, str]]:
    blocks = _evidence(evidence) or "(none)"
    missing = (f"\n\nUnavailable sources (rule 7 applies): {', '.join(unavailable)}" if unavailable else "")
    return [
        {"role": "system", "content": TRIAGE_SYSTEM},
        {"role": "user", "content": f"Evidence:\n\n{blocks}{missing}\n\nIncident:\n{incident}"},
    ]


JUDGE_PROMPT_VERSION = "judge/4"

# The judge only lists the sentence's facts and compares each with the source; the yes/no rule is applied in code
# (evals/triage_eval.py: supported), because a small model follows a checklist far better than a rule with exceptions.
# "2 hours" is settings.triage_deploy_window_h, the deploys triage treats as recent (tested in test_prompts).
JUDGE_SYSTEM = """\
You check one citation in an incident triage brief. You get the incident (its service and when it started), one \
sentence from the brief, and the text of one source the sentence cites. The sentence may cite other sources too.

First split the sentence into its separate facts: each a short statement about a service, a number, a cause, an \
event, a time or a command. Take facts only from the sentence, never from the source. Keep each fact framed the way \
the sentence frames it: "a deploy to X is a candidate cause" stays a candidate, not "X caused it". Leave out \
statements about the evidence or the brief itself ("the evidence does not cover X", "the evidence points to Y"), \
and facts the incident line already gives (its service, its start): they say nothing about the source.

Then compare each fact with the source and give it a status:
- stated: the source says this, in any wording. "Shortly before the incident" means up to 2 hours before its \
start; a deploy record says how long before or after the start it was. A candidate cause is stated when the \
source shows it happening in that time or names it as a possible or common cause.
- contradicted: the source says something that can't be true at the same time: a different service, number, cause \
or kind of failure; an event the sentence places shortly before the incident that the source dates after its start \
or more than 2 hours before; a possibility in the source stated as a certainty; or what the source says about a past \
incident stated as a fact about this incident.
- not_stated: the source says nothing either way.

Answer in JSON: {"facts": [{"fact": "<short statement>", "status": "stated" or "not_stated" or "contradicted"}]}"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {
        "type": "object",
        "properties": {"fact": {"type": "string"},
                       "status": {"type": "string", "enum": ["stated", "not_stated", "contradicted"]}},
        "required": ["fact", "status"],
    }}},
    "required": ["facts"],
}


def judge_messages(incident: str, claim: str, source: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": f"Incident:\n{incident}\n\nSentence:\n{claim}\n\nSource:\n{source}"},
    ]
