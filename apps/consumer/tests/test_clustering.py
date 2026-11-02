import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pagerwise_consumer.clustering import Candidate, Decision, RecentAlert, decide, neighbourhood

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
EDGES = {("payments", "ledger"), ("ledger", "postgres-primary"), ("api-gateway", "payments")}
OLD, OTHER, THIRD = (uuid.UUID(int=i) for i in (1, 2, 3))


def ago(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


def recent(minutes: float, incident=OLD, status="open") -> RecentAlert:
    return RecentAlert(incident, ago(minutes), status)


def candidate(service: str, similarity: float, minutes: float = 1, incident=OTHER, status="open") -> Candidate:
    return Candidate(incident, service, status, ago(minutes), similarity)


CASES = [
    # (name, alert service, recent same-fingerprint alerts, candidates, expected)
    ("same fingerprint 9 minutes ago joins its incident",
     "ledger", [recent(9)], [], Decision("fingerprint", OLD)),
    ("same fingerprint wins over a more similar incident",
     "ledger", [recent(2)], [candidate("ledger", 0.99)], Decision("fingerprint", OLD)),
    ("same fingerprint 11 minutes ago is too old: falls through to a new incident",
     "ledger", [recent(11)], [], Decision("new")),
    ("same fingerprint into a resolved incident doesn't count",
     "ledger", [recent(2, status="resolved")], [], Decision("new")),
    ("similar incident in the same service joins",
     "ledger", [], [candidate("ledger", 0.91)], Decision("similar", OTHER, 0.91)),
    ("similar incident one hop away (a dependency) joins",
     "ledger", [], [candidate("postgres-primary", 0.90)], Decision("similar", OTHER, 0.90)),
    ("similar incident one hop away (a caller) joins",
     "ledger", [], [candidate("payments", 0.88)], Decision("similar", OTHER, 0.88)),
    ("two hops away doesn't join, however similar",
     "ledger", [], [candidate("api-gateway", 0.97)], Decision("new")),
    ("similarity just under 0.86 doesn't join",
     "ledger", [], [candidate("ledger", 0.859)], Decision("new")),
    ("similarity exactly 0.86 joins",
     "ledger", [], [candidate("ledger", 0.86)], Decision("similar", OTHER, 0.86)),
    ("incident quiet for 16 minutes doesn't join",
     "ledger", [], [candidate("ledger", 0.95, minutes=16)], Decision("new")),
    ("resolved candidate doesn't join",
     "ledger", [], [candidate("ledger", 0.95, status="resolved")], Decision("new")),
    ("the most similar of two eligible incidents wins",
     "ledger", [], [candidate("ledger", 0.88), candidate("payments", 0.93, incident=THIRD)],
     Decision("similar", THIRD, 0.93)),
    ("a similarity tie goes to the same service",
     "ledger", [], [candidate("payments", 0.9, incident=THIRD), candidate("ledger", 0.9)],
     Decision("similar", OTHER, 0.9)),
]


@pytest.mark.parametrize(("name", "service", "recent_alerts", "candidates", "expected"), CASES, ids=[c[0] for c in CASES])
def test_clustering_decision(name, service, recent_alerts, candidates, expected):
    assert decide(service, NOW, recent_alerts, candidates, EDGES) == expected


def test_neighbourhood_is_one_hop_both_ways():
    assert neighbourhood("ledger", EDGES) == {"ledger", "payments", "postgres-primary"}
    assert neighbourhood("api-gateway", EDGES) == {"api-gateway", "payments"}
    assert neighbourhood("unknown", EDGES) == {"unknown"}
