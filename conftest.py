"""Fixtures shared by every package's tests. Container fixtures are only started by integration tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent
REDPANDA_IMAGE = "docker.redpanda.com/redpandadata/redpanda:v26.2.6"  # same as docker-compose.yml


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A throwaway Postgres with pgvector and every migration applied, then rolled back and re-applied, so each
    run also proves the migrations are reversible."""
    from alembic import command
    from alembic.config import Config
    from testcontainers.community.postgres import PostgresContainer

    from pagerwise_api.settings import settings

    with PostgresContainer("pgvector/pgvector:0.8.7-pg18-trixie", driver="asyncpg") as container:
        url = container.get_connection_url()
        settings.database_url = url  # migrations/env.py reads it from here
        config = Config(str(REPO / "alembic.ini"))
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield url


@pytest.fixture
def kafka_bootstrap() -> Iterator[str]:
    """A fresh Redpanda per test, with Pagerwise's topics, so no test sees another's messages or offsets."""
    import asyncio

    from testcontainers.community.kafka import RedpandaContainer

    from pagerwise_kafka import create_topics

    with RedpandaContainer(REDPANDA_IMAGE) as container:
        bootstrap = container.get_bootstrap_server()
        asyncio.run(create_topics(bootstrap))
        yield bootstrap
