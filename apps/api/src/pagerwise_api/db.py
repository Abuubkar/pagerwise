import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, LargeBinary, SmallInteger, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pagerwise_api.settings import settings

# bge-small-en-v1.5 vectors. Changing the embedding model changes this, and needs a migration (slice 6).
EMBEDDING_DIM = 384

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


class Base(DeclarativeBase):
    pass


class Document(Base):
    """One source file (a runbook for now). Reloaded only when its content hash changes."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    source_type: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(String(512), unique=True)
    service: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    # "Payments: high p99 latency > Check the ledger pool"; also prefixed to the embedded text.
    heading_path: Mapped[str] = mapped_column(String(1024))
    text: Mapped[str]
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIM))


class Answer(Base):
    """Every /v1/ask answer, with what produced it, so a bad answer can be traced to its prompt and model."""

    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    question: Mapped[str]
    answer: Mapped[str]
    verdict: Mapped[str] = mapped_column(String(32))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    problems: Mapped[list[str]] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    # Ollama's own durations, in ms: total includes model load; prompt eval and eval are the two phases.
    total_ms: Mapped[int] = mapped_column(Integer)
    load_ms: Mapped[int] = mapped_column(Integer)
    prompt_eval_ms: Mapped[int] = mapped_column(Integer)
    eval_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Incident(Base):
    """Created by hand for now; alerts open them from slice 4. `version` goes up on every change, and a triage
    belongs to the version it was run on."""

    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_opened_at_id", text("opened_at DESC"), text("id DESC")),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    title: Mapped[str] = mapped_column(String(300))
    service: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    summary: Mapped[str] = mapped_column(server_default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TriageRun(Base):
    """One triage of one incident version. queued -> running -> completed | failed. At most one queued or
    running run per incident version (partial unique index), which is what turns a second request into a 409."""

    __tablename__ = "triage_runs"
    __table_args__ = (
        Index(
            "uq_triage_runs_active",
            "incident_id",
            "incident_version",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    incident_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    # The tagged evidence the prompt was built from: [{tag, source_type, source_id, chunk_id, heading_path, text}].
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    raw_text: Mapped[str] = mapped_column(server_default="")
    brief: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    verdict: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    problems: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    ttft_ms: Mapped[int | None] = mapped_column(Integer)  # stream opened -> first answer token, wall clock
    total_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Renewed while the model streams; a running run whose heartbeat is stale was abandoned (process died).
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertEvent(Base):
    """One alert as consumed from Kafka. event_id comes from the producer, so a redelivered message inserts nothing
    (ON CONFLICT DO NOTHING). Slice 4 turns this into a table partitioned by day."""

    __tablename__ = "alert_events"

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    service: Mapped[str] = mapped_column(String(128), index=True)
    fingerprint: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    labels: Mapped[dict[str, str]] = mapped_column(JSONB, server_default="{}")
    summary: Mapped[str]
    attempt: Mapped[int] = mapped_column(SmallInteger, server_default="0")  # transient failures before it landed
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeadLetter(Base):
    """A message that reached alerts.dlq, kept with its raw bytes (it may not even be JSON) so it can be inspected
    and replayed. One row per original message, however many times it was redelivered."""

    __tablename__ = "dead_letters"
    __table_args__ = (UniqueConstraint("original_topic", "original_partition", "original_offset"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    original_topic: Mapped[str] = mapped_column(String(255))
    original_partition: Mapped[int] = mapped_column(Integer)
    original_offset: Mapped[int] = mapped_column(BigInteger)
    dlq_offset: Mapped[int] = mapped_column(BigInteger, index=True)
    key: Mapped[str | None] = mapped_column(String(255), index=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    headers: Mapped[dict[str, str]] = mapped_column(JSONB, server_default="{}")
    error_class: Mapped[str] = mapped_column(String(128))
    error: Mapped[str]
    attempt: Mapped[int] = mapped_column(SmallInteger)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replay_count: Mapped[int] = mapped_column(Integer, server_default="0")
