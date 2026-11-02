from pagerwise_api.citations import parse_answer

SUPPLIED = {"C1", "C2", "C3"}


def test_valid_tags_map_in_order_of_first_use():
    parsed = parse_answer("Pool is 40 [C2]. Payments waits on it [C1][C2].", SUPPLIED)
    assert parsed.verdict == "ANSWERED"
    assert parsed.tags == ["C2", "C1"]
    assert parsed.problems == []


def test_unknown_tag_rejects_the_answer():
    parsed = parse_answer("Pool is 40 [C2]. Failover takes 30 s [C9].", SUPPLIED)
    assert parsed.verdict == "REJECTED"
    assert parsed.problems == ["unknown tag [C9]"]


def test_answer_without_tags_is_rejected():
    parsed = parse_answer("The ledger pool is probably exhausted.", SUPPLIED)
    assert parsed.verdict == "REJECTED"
    assert parsed.problems == ["no citations"]


def test_grouped_tag_is_malformed():
    parsed = parse_answer("Pool is 40 [C1, C2].", SUPPLIED)
    assert parsed.verdict == "REJECTED"
    assert parsed.problems == ["malformed tag [C1, C2]"]


def test_insufficient_evidence_is_an_abstention():
    parsed = parse_answer("INSUFFICIENT_EVIDENCE", SUPPLIED)
    assert parsed.verdict == "INSUFFICIENT_EVIDENCE"
    assert parsed.tags == []
