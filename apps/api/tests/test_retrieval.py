import uuid

import pytest

from pagerwise_api.retrieval import reciprocal_rank_fusion

A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


def test_rrf_matches_a_hand_computed_example():
    # full-text: A B C   vector: C A D   (k = 60, ranks start at 1)
    # A: 1/61 + 1/62 = 0.032522    C: 1/63 + 1/61 = 0.032266
    # B: 1/62        = 0.016129    D: 1/63        = 0.015873
    fused = reciprocal_rank_fusion([[A, B, C], [C, A, D]])
    assert [item for item, _ in fused] == [A, C, B, D]
    assert [round(score, 6) for _, score in fused] == [0.032522, 0.032266, 0.016129, 0.015873]


def test_agreeing_lower_in_both_lists_beats_first_in_one():
    # B is 2nd in both; A is 1st in one only.
    fused = reciprocal_rank_fusion([[A, B], [C, B]])
    assert fused[0][0] == B
    assert fused[0][1] == pytest.approx(2 / 62)


def test_one_empty_ranking_keeps_the_other_in_order():
    """Full-text search often finds nothing for a vague question; vector order must survive unchanged."""
    assert [item for item, _ in reciprocal_rank_fusion([[], [D, C, B]])] == [D, C, B]
