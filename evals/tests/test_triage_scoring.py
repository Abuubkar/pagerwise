import pytest
from sklearn.metrics import cohen_kappa_score

from triage_eval import (
    cause_hits,
    claims,
    named_categories,
    pair_supported,
    specific_tokens,
    supported,
    with_deploy_timing,
)


def test_categories_in_order_of_first_mention():
    text = "Ledger ran out of database connections after a deploy; latency rose as the pool drained [C1]."
    assert named_categories(text) == ["connection-pool", "bad-deploy", "high-latency"]


def test_identifiers_and_runbook_cause_names_count():
    text = ("`KafkaBrokerLatencyHigh` fired because `kafka_broker_p99_latency_ms` stayed high; the most common cause "
            "is garbage collection pauses [C1]. A deploy in the last hour makes that less likely [C1].")
    assert named_categories(text)[0] == "high-latency"
    assert cause_hits(text, {"category": "high-latency", "component": "kafka-broker"}) == (True, True)


def test_root_cause_hit_needs_the_category_first_and_the_component_named():
    gold = {"category": "connection-pool", "component": "ledger"}
    assert cause_hits("The ledger connection pool is exhausted [C1].", gold) == (True, True)
    assert cause_hits("A deploy to ledger, then pool exhaustion [C1][C2].", gold) == (False, True)  # second named
    assert cause_hits("The connection pool is exhausted [C1].", gold) == (False, False)  # component never named
    assert cause_hits("INSUFFICIENT_EVIDENCE", gold) == (False, False)
    dep = {"category": "dependency-timeout", "component": "postgres-primary"}
    assert cause_hits("Calls to postgres primary are timing out [C2].", dep) == (True, True)  # 'postgres primary'


def test_claims_split_sentences_and_keep_only_supplied_tags():
    raw = ("## Likely cause\nThe pool is exhausted [C1]. Payments waits on ledger [C2][C9].\n\n## Blast radius\n"
           "Payments callers see errors [C1].\n\n## First steps\n1. Run `ledgerctl pool stats` [C1].\n\n"
           "## Similar incidents\nNone in the evidence.\n")
    evidence = [{"tag": "C1", "source_type": "runbook", "text": "pool text"},
                {"tag": "C2", "source_type": "postmortem", "text": "pm text"}]
    found = claims(raw, evidence)
    assert [(c["section"], [s["tag"] for s in c["sources"]]) for c in found] == [
        ("likely_cause", ["C1"]), ("likely_cause", ["C2"]), ("blast_radius", ["C1"]), ("first_steps", ["C1"])]
    assert found[0]["claim"] == "The pool is exhausted ."  # tags stripped for the judge


def test_cohen_kappa_on_a_hand_computed_example():
    # Observed agreement 3/4. Chance: labels 50% yes, judge 25% yes -> 0.5*0.25 + 0.5*0.75 = 0.5.
    # kappa = (0.75 - 0.5) / (1 - 0.5) = 0.5
    assert cohen_kappa_score([True, True, False, False], [True, False, False, False]) == pytest.approx(0.5)


def test_judge_rule_is_applied_to_the_per_fact_statuses():
    stated, missing, wrong = ({"fact": "x", "status": s} for s in ("stated", "not_stated", "contradicted"))
    assert supported([stated, stated], cites=1)
    assert not supported([stated, missing], cites=1)  # one source must carry every fact
    assert supported([stated, missing], cites=2)  # the other source may carry the rest
    assert not supported([missing, missing], cites=2)
    assert not supported([stated, wrong], cites=3)  # a contradiction always fails
    assert not supported([], cites=1)


def test_deploy_sources_get_their_offset_from_the_incident_start():
    # una-11 (payments) started 07:55:30; this deploy finished 13 minutes later.
    deploy = "Deploy gdep-07: api-gateway version 2.31.1 deployed at 2026-10-28T08:08:43.659038Z by Golden Set."
    assert with_deploy_timing(deploy, "una-11").endswith("(This deploy was 13 minutes after the incident started.)")
    assert with_deploy_timing("# Runbook text", "una-11") == "# Runbook text"


# Case ans-21: inventory, started 2026-10-28T10:48. Its alerts quote inventory_p99_latency_ms.
PM = "# Postmortem: inventory CPU saturation (2026-06-16)\n- Callers affected: orders, search.\n- 12,273 customers saw errors."


def test_checkable_content_leaves_out_what_the_incident_gives():
    assert specific_tokens("`inventory_p99_latency_ms` is high on inventory; 12,273 customers and orders", "ans-21") == [
        "12273", "orders"]
    assert specific_tokens("Check the dashboard.", "ans-21") == []


def test_each_citation_rule():
    late = "Deploy gdep-11: search version 1.0.0 deployed at 2026-10-28T11:00:00Z by Golden Set."
    assert pair_supported("ans-21", "likely_cause", "A deploy to search 1.0.0 is a candidate.", late, []) is False
    # Postmortem content in a cause or impact sentence must be framed as past.
    assert pair_supported("ans-21", "blast_radius", "12,273 customers saw errors.", PM, []) is False
    assert pair_supported("ans-21", "blast_radius", "Past incidents saw 12,273 customers hit.", PM, []) is True
    # Every token must be in some cited source; this one must hold at least one.
    assert pair_supported("ans-21", "blast_radius", "Past incidents hit 12,273 and 4,554 customers.", PM, []) is False
    assert pair_supported("ans-21", "blast_radius", "Past incidents hit 12,273 and 4,554 customers.", PM,
                          ["4,554 customers saw errors."]) is True
    assert pair_supported("ans-21", "first_steps", "Check the dashboard.", PM, []) is None
