import pytest

from pagerwise_api.citations import (
    CitationEvent,
    SectionCompleteEvent,
    TagScanner,
    TokenEvent,
    parse_brief,
)

SUPPLIED = {"C1", "C2", "C3"}

VALID = """## Likely cause
Ledger still writes to the demoted primary [C1].

## Blast radius
Every ledger write fails until the pools recycle [C1][C2].

## First steps
1. Recycle the pools: `ledgerctl pool recycle --all-pods` [C1].

## Similar incidents
None in the evidence."""


def scan(pieces: list[str]) -> list:
    scanner = TagScanner(SUPPLIED)
    events = [e for p in pieces for e in scanner.feed(p)]
    return events + scanner.finish()


def test_tag_split_across_two_pieces_is_one_citation_after_it_closes():
    events = scan(["## Likely cause\nPool is low [C", "2]. Next."])
    citations = [e for e in events if isinstance(e, CitationEvent)]
    assert citations == [CitationEvent("C2", "likely_cause")]
    # The citation comes right after the token that closed the tag, not before.
    i = events.index(citations[0])
    assert events[i - 1] == TokenEvent("2]")


def test_tokens_concatenate_to_exactly_the_model_text_whatever_the_split():
    for size in (1, 3, 7, 50):
        pieces = [VALID[i : i + size] for i in range(0, len(VALID), size)]
        assert "".join(e.text for e in scan(pieces) if isinstance(e, TokenEvent)) == VALID


def test_sections_complete_in_order_and_citations_land_in_their_section():
    events = scan([VALID[i : i + 5] for i in range(0, len(VALID), 5)])
    assert [e.section for e in events if isinstance(e, SectionCompleteEvent)] == [
        "likely_cause", "blast_radius", "first_steps", "similar_incidents",
    ]
    assert [(e.tag, e.section) for e in events if isinstance(e, CitationEvent)] == [
        ("C1", "likely_cause"), ("C1", "blast_radius"), ("C2", "blast_radius"), ("C1", "first_steps"),
    ]


def test_unknown_tag_gets_no_citation_event():
    events = scan(["## Likely cause\nSomething [C9]."])
    assert not [e for e in events if isinstance(e, CitationEvent)]


def test_valid_brief_parses_with_verdict_and_tags():
    parsed = parse_brief(VALID, SUPPLIED)
    assert parsed.problems == []
    assert parsed.verdict == "CAUSE_IDENTIFIED"
    assert parsed.sections["blast_radius"].tags == ["C1", "C2"]
    assert parsed.sections["similar_incidents"].tags == []


def test_insufficient_evidence_in_likely_cause_is_an_abstention():
    text = VALID.replace("Ledger still writes to the demoted primary [C1].", "INSUFFICIENT_EVIDENCE")
    assert parse_brief(text, SUPPLIED).verdict == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize(
    ("broken", "problem"),
    [
        (VALID.replace("## Blast radius", "## Impact"), "sections are"),
        (VALID.replace("[C2]", "[C7]"), "blast_radius: unknown tag [C7]"),
        (VALID.replace("None in the evidence.", "Looks like last week's outage."), "similar_incidents: no citations"),
        ("Here is the brief.\n" + VALID, "text before the first section"),
        (VALID.replace("Every ledger write fails until the pools recycle [C1][C2].", ""), "blast_radius: empty"),
    ],
)
def test_contract_breaks_have_no_verdict_and_say_why(broken, problem):
    parsed = parse_brief(broken, SUPPLIED)
    assert parsed.verdict is None
    assert any(p.startswith(problem) for p in parsed.problems), parsed.problems
