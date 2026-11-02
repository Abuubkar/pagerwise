"""Checks a model answer against the citation contract in prompts.py. Deterministic: no model involved."""

import re
from dataclasses import dataclass, field
from typing import Literal

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
TAG_RE = re.compile(r"\[(C\d+)\]")
# Anything that looks like an attempt at a tag, e.g. "[C1, C2]" or "[C 3]", which TAG_RE doesn't accept.
TAG_LIKE_RE = re.compile(r"\[\s*C\s*\d[^\]]*\]")

Verdict = Literal["ANSWERED", "INSUFFICIENT_EVIDENCE", "REJECTED"]


@dataclass
class ParsedAnswer:
    verdict: Verdict
    tags: list[str]  # cited tags in order of first use, each one of the supplied tags
    problems: list[str] = field(default_factory=list)


def parse_answer(answer: str, supplied_tags: set[str]) -> ParsedAnswer:
    """ANSWERED needs at least one tag and only tags that were supplied. An answer that says
    INSUFFICIENT_EVIDENCE anywhere is an abstention, whatever else it says: it names no cause."""
    if INSUFFICIENT_EVIDENCE in answer:
        return ParsedAnswer(verdict="INSUFFICIENT_EVIDENCE", tags=[])

    problems = [f"malformed tag {m}" for m in TAG_LIKE_RE.findall(answer) if not TAG_RE.fullmatch(m)]
    tags: list[str] = []
    for tag in TAG_RE.findall(answer):
        if tag not in supplied_tags:
            problems.append(f"unknown tag [{tag}]")
        elif tag not in tags:
            tags.append(tag)
    if not tags and not problems:
        problems.append("no citations")
    if problems:
        return ParsedAnswer(verdict="REJECTED", tags=tags, problems=list(dict.fromkeys(problems)))
    return ParsedAnswer(verdict="ANSWERED", tags=tags)
