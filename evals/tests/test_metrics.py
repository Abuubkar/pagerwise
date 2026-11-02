import pytest

from metrics import mrr_at_k, pairwise_prf, percentile, recall_at_k


def test_recall_and_mrr_on_a_hand_computed_ranking():
    ranked = ["a", "x", "b", "y", "z"]
    gold = {"b", "c"}
    assert recall_at_k(ranked, gold, 3) == 0.5  # b is in the top 3, c isn't anywhere
    assert recall_at_k(ranked, gold, 1) == 0.0
    assert mrr_at_k(ranked, gold, 10) == pytest.approx(1 / 3)  # first gold at rank 3
    assert mrr_at_k(ranked, gold, 2) == 0.0  # not within the first 2
    assert recall_at_k(ranked, set(), 8) == 0.0


def test_pairwise_f1_on_a_hand_computed_clustering():
    # Gold: {1,2,3} and {4,5}. Predicted: {1,2} and {3,4,5}.
    gold = {1: "A", 2: "A", 3: "A", 4: "B", 5: "B"}
    predicted = {1: "p", 2: "p", 3: "q", 4: "q", 5: "q"}
    # Predicted pairs: 12, 34, 35, 45 (4). Gold pairs: 12, 13, 23, 45 (4). Both: 12, 45 (2).
    precision, recall, f1 = pairwise_prf(predicted, gold)
    assert (precision, recall, f1) == (0.5, 0.5, 0.5)


def test_pairwise_f1_extremes():
    gold = {1: "A", 2: "A", 3: "B"}
    assert pairwise_prf(gold, gold) == (1.0, 1.0, 1.0)
    everything_split = {1: 1, 2: 2, 3: 3}  # no predicted pairs: precision is vacuous, recall 0
    assert pairwise_prf(everything_split, gold)[1:] == (0.0, 0.0)
    everything_merged = {1: "x", 2: "x", 3: "x"}  # 3 predicted pairs, 1 right
    assert pairwise_prf(everything_merged, gold) == pytest.approx((1 / 3, 1.0, 0.5))


def test_nearest_rank_percentile():
    values = list(range(1, 21))  # 1..20
    assert percentile(values, 50) == 10
    assert percentile(values, 95) == 19
    assert percentile(values, 100) == 20
    assert percentile([7], 95) == 7
