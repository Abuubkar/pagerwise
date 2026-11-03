"""Checks model output against the citation contracts in prompts.py. Deterministic: no model involved.

Three users of one tag syntax: parse_answer (/v1/ask), parse_brief (the four-section triage brief, checked once the
stream ends) and TagScanner (emits citation and section events while the brief streams). LikelyCauseGate sits in
front of the last two: it turns the model's cause decision line into the brief's Likely cause."""

import re
from dataclasses import dataclass, field
from typing import Literal

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
TAG_RE = re.compile(r"\[(C\d+)\]")
# Anything that looks like an attempt at a tag, e.g. "[C1, C2]" or "[C 3]", which TAG_RE doesn't accept.
TAG_LIKE_RE = re.compile(r"\[\s*C\s*\d[^\]]*\]")

Verdict = Literal["ANSWERED", "INSUFFICIENT_EVIDENCE", "REJECTED"]


def scan_tags(text: str, supplied_tags: set[str]) -> tuple[list[str], list[str]]:
    """(supplied tags in order of first use, problems): unknown and malformed tags are problems."""
    problems = [f"malformed tag {m}" for m in TAG_LIKE_RE.findall(text) if not TAG_RE.fullmatch(m)]
    tags: list[str] = []
    for tag in TAG_RE.findall(text):
        if tag not in supplied_tags:
            problems.append(f"unknown tag [{tag}]")
        elif tag not in tags:
            tags.append(tag)
    return tags, list(dict.fromkeys(problems))


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
    tags, problems = scan_tags(answer, supplied_tags)
    if not tags and not problems:
        problems.append("no citations")
    if problems:
        return ParsedAnswer(verdict="REJECTED", tags=tags, problems=problems)
    return ParsedAnswer(verdict="ANSWERED", tags=tags)


# The brief's section contract: these headings, in this order, each exactly once.
SECTIONS = {
    "Likely cause": "likely_cause",
    "Blast radius": "blast_radius",
    "First steps": "first_steps",
    "Similar incidents": "similar_incidents",
}
NO_SIMILAR = "None in the evidence."
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ParsedSection:
    text: str
    tags: list[str]


@dataclass
class ParsedBrief:
    verdict: Literal["CAUSE_IDENTIFIED", "INSUFFICIENT_EVIDENCE"] | None  # None when the contract is broken
    sections: dict[str, ParsedSection]
    problems: list[str]


def parse_brief(text: str, supplied_tags: set[str]) -> ParsedBrief:
    """The four sections must appear in order with nothing before the first. Likely cause, Blast radius and First
    steps each either cite at least one supplied tag or are exactly INSUFFICIENT_EVIDENCE; Similar incidents cites
    or says NO_SIMILAR. No unknown or malformed tags anywhere. The verdict follows Likely cause."""
    problems: list[str] = []
    headings = list(SECTION_RE.finditer(text))
    names = [m.group(1) for m in headings]
    if names != list(SECTIONS):
        problems.append(f"sections are {names}, expected {list(SECTIONS)}")
    if headings and text[: headings[0].start()].strip():
        problems.append("text before the first section")

    sections: dict[str, ParsedSection] = {}
    for i, match in enumerate(headings):
        key = SECTIONS.get(match.group(1))
        if key is None or key in sections:
            continue
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[match.end() : end].strip()
        tags, tag_problems = scan_tags(body, supplied_tags)
        problems.extend(f"{key}: {p}" for p in tag_problems)
        sections[key] = ParsedSection(text=body, tags=tags)
        abstained = body == INSUFFICIENT_EVIDENCE or (key == "similar_incidents" and body == NO_SIMILAR)
        if not body:
            problems.append(f"{key}: empty")
        elif not tags and not abstained and not tag_problems:
            problems.append(f"{key}: no citations")

    likely = sections.get("likely_cause")
    verdict: Literal["CAUSE_IDENTIFIED", "INSUFFICIENT_EVIDENCE"] | None = None
    if not problems and likely is not None:
        verdict = "INSUFFICIENT_EVIDENCE" if likely.text == INSUFFICIENT_EVIDENCE else "CAUSE_IDENTIFIED"
    return ParsedBrief(verdict=verdict, sections=sections, problems=problems)


# The first line of Likely cause, where the model names the item that describes the incident's failure (triage/6).
MATCH_RE = re.compile(r"^[*_]*match[*_]*\s*:[*_]*\s*(.*)$", re.IGNORECASE)
LEADING_TAGS_RE = re.compile(r"^(?:\s*\[C\d+\][\s,.;]*)+")
Decision = Literal["match", "none", "not_a_cause", "missing"]


class LikelyCauseGate:
    """Applies the brief's cause decision in code, between the model and everything else (stream, parse, replay).
    Likely cause must open with a line "Match: [Cn]" naming a runbook or postmortem, or "Match: none". The line
    itself is dropped. If it names no item in cause_tags (none, or only a deploy: a deploy alone is not a cause),
    the section becomes exactly INSUFFICIENT_EVIDENCE, whatever the model wrote after it. A small model reasons its
    way to "nothing matches" far more reliably than it writes the token (docs/adr/0010).

    Text passes through as it arrives, except from the Likely cause heading until its decision line has ended, and
    in a dropped section until the next heading line has. decision stays "missing" if the section has no decision
    line (it then passes through unchanged and the caller treats the brief as broken), None if there's no section."""

    def __init__(self, cause_tags: set[str]):
        self.cause_tags = cause_tags
        self.state: Literal["before", "deciding", "passing", "dropping"] = "before"
        self.line = ""  # the current line so far
        self.held = ""  # text held back while deciding
        self.decision: Decision | None = None

    def feed(self, piece: str) -> str:
        out: list[str] = []
        for segment in re.split(r"(?<=\n)", piece):
            if segment:
                out.append(self._segment(segment))
        return "".join(out)

    def finish(self) -> str:
        if self.state == "deciding" and self.line.strip():
            return self._decide(self.line)
        return self.held if self.state == "deciding" else ""

    def _segment(self, segment: str) -> str:
        self.line += segment
        complete, line = segment.endswith("\n"), self.line
        if complete:
            self.line = ""
        if self.state == "before":
            heading = SECTION_RE.match(line.rstrip("\n")) if complete else None
            if heading and SECTIONS.get(heading.group(1)) == "likely_cause":
                self.state, self.decision = "deciding", "missing"
            return segment
        if self.state == "deciding":
            self.held += segment
            return self._decide(line) if complete and line.strip() else ""
        if self.state == "dropping":
            if complete and SECTION_RE.match(line.rstrip("\n")):
                self.state = "passing"
                return line
            return ""
        return segment

    def _decide(self, line: str) -> str:
        held, self.held = self.held, ""
        match = MATCH_RE.match(line.strip())
        if match is None:
            self.state = "passing"
            return held
        tags = TAG_RE.findall(match.group(1))
        if any(t in self.cause_tags for t in tags):
            self.state, self.decision = "passing", "match"
            rest = LEADING_TAGS_RE.sub("", match.group(1))  # the model sometimes goes on with the cause on this line
            return f"{rest}\n" if rest else ""
        self.state, self.decision = "dropping", ("not_a_cause" if tags else "none")
        return f"{INSUFFICIENT_EVIDENCE}\n\n"


def gate_brief(text: str, cause_tags: set[str]) -> tuple[str, Decision | None]:
    """LikelyCauseGate on a whole text: (the brief as streamed, the decision)."""
    gate = LikelyCauseGate(cause_tags)
    gated = gate.feed(text) + gate.finish()
    return gated, gate.decision


@dataclass
class TokenEvent:
    text: str


@dataclass
class CitationEvent:
    tag: str
    section: str | None  # None if the tag came before any known section heading


@dataclass
class SectionCompleteEvent:
    section: str


ScanEvent = TokenEvent | CitationEvent | SectionCompleteEvent


class TagScanner:
    """Turns streamed text into token, citation and section_complete events, in text order. Model output arrives
    in arbitrary pieces, so a tag ("[C1" + "2]") or a heading line can be split across them: a citation is emitted
    once its closing bracket has arrived, and a section is complete once the next heading line has ended (or the
    stream has). Token events are split at those points and concatenate to exactly what the model wrote."""

    def __init__(self, supplied_tags: set[str]):
        self.supplied = supplied_tags
        self.text = ""
        self.emitted = 0  # text before this offset has gone out as token events
        self.tag_pos = 0  # tags before this offset have been handled
        self.line_pos = 0  # complete lines before this offset have been checked for headings
        self.section: str | None = None
        self.cited: set[tuple[str | None, str]] = set()

    def feed(self, piece: str) -> list[ScanEvent]:
        self.text += piece
        events: list[ScanEvent] = []
        # Walk complete lines and tags in text order, so a tag lands in the section it was written under.
        while True:
            newline = self.text.find("\n", self.line_pos)
            tag = TAG_RE.search(self.text, self.tag_pos)
            if tag and (newline == -1 or tag.start() < newline):
                self.tag_pos = tag.end()
                found = self._cite(tag.group(1))
                at = tag.end()
            elif newline != -1:
                found = self._line(self.text[self.line_pos : newline])
                self.line_pos = newline + 1
                self.tag_pos = max(self.tag_pos, self.line_pos)
                at = newline + 1
            else:
                break
            if found:
                events.extend(self._tokens_until(at))
                events.extend(found)
        events.extend(self._tokens_until(len(self.text)))
        return events

    def finish(self) -> list[ScanEvent]:
        """Call once the stream ends: the last line may have no newline, and the last section is complete."""
        events = self._line(self.text[self.line_pos :])
        self.line_pos = len(self.text)
        if self.section:
            events.append(SectionCompleteEvent(self.section))
            self.section = None
        return events

    def _tokens_until(self, offset: int) -> list[ScanEvent]:
        if offset <= self.emitted:
            return []
        text, self.emitted = self.text[self.emitted : offset], offset
        return [TokenEvent(text)]

    def _cite(self, tag: str) -> list[ScanEvent]:
        if tag not in self.supplied or (self.section, tag) in self.cited:
            return []  # unknown tags are parse_brief's job; repeats in one section are one citation
        self.cited.add((self.section, tag))
        return [CitationEvent(tag, self.section)]

    def _line(self, line: str) -> list[ScanEvent]:
        heading = SECTION_RE.match(line)
        if not heading or heading.group(1) not in SECTIONS:
            return []
        events: list[ScanEvent] = [SectionCompleteEvent(self.section)] if self.section else []
        self.section = SECTIONS[heading.group(1)]
        return events
