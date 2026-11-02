"""The eval's metrics, as plain functions over ids: unit-tested in evals/tests/test_metrics.py."""

from collections import Counter
from collections.abc import Hashable, Mapping, Sequence
from math import comb


def recall_at_k(ranked: Sequence[Hashable], gold: set, k: int) -> float:
    """Share of the gold items that appear in the first k results. 0 if there is no gold (not applicable)."""
    if not gold:
        return 0.0
    return len(gold & set(ranked[:k])) / len(gold)


def mrr_at_k(ranked: Sequence[Hashable], gold: set, k: int) -> float:
    """1 / rank of the first gold item within the first k results (ranks start at 1); 0 if none is there."""
    for rank, item in enumerate(ranked[:k], start=1):
        if item in gold:
            return 1.0 / rank
    return 0.0


def pairwise_prf(predicted: Mapping[Hashable, Hashable], gold: Mapping[Hashable, Hashable]) -> tuple[float, float, float]:
    """Clustering quality over pairs of items: a pair is predicted together if both items got the same predicted
    cluster, and truly together if they share a gold cluster. Returns (precision, recall, F1). Counts pairs per
    cluster with n-choose-2 instead of listing them, so it's fast for thousands of items."""
    items = gold.keys() & predicted.keys()
    together_predicted = sum(comb(n, 2) for n in Counter(predicted[i] for i in items).values())
    together_gold = sum(comb(n, 2) for n in Counter(gold[i] for i in items).values())
    together_both = sum(comb(n, 2) for n in Counter((predicted[i], gold[i]) for i in items).values())
    precision = together_both / together_predicted if together_predicted else 1.0
    recall = together_both / together_gold if together_gold else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100): the smallest value with at least q% of the values at or below it."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * q // 100))  # ceil(n * q / 100)
    return ordered[int(rank) - 1]
