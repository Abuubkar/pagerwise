import json

from run import check_gates, known_misses


def test_only_misses_the_baseline_also_has_are_known(tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"metrics": {"triage.abstention": 0.4, "triage.format_validity": 0.97}}))
    missed = check_gates({"triage.abstention": 0.3, "triage.format_validity": 0.9, "retrieval.recall_at_8": 0.5})
    assert len(missed) == 3
    # Abstention was already under its gate on the baseline; format validity passed there; recall isn't in it.
    assert known_misses(missed, baseline) == [m for m in missed if m.startswith("triage.abstention")]
