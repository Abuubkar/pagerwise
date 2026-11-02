from pathlib import Path

from pagerwise_api.graphql import schema

REPO = Path(__file__).resolve().parents[3]


def test_checked_in_schema_matches_the_code():
    # contracts/schema.graphql is what UI codegen reads; `make codegen` rewrites it after a GraphQL change.
    assert (REPO / "contracts" / "schema.graphql").read_text().strip() == schema.as_str().strip()
