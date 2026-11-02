import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
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
