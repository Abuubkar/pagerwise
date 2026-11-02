"""Request and response models of the REST API. contracts/openapi.yaml is the contract; these must match it
(`make contract-check`)."""

import enum
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROBLEMS_URL = "https://github.com/Abuubkar/pagerwise/blob/main/docs/problems.md"


class ProblemCode(enum.StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_CURSOR = "invalid_cursor"
    NOT_FOUND = "not_found"
    TRIAGE_IN_PROGRESS = "triage_in_progress"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROMPT_TOO_LONG = "prompt_too_long"
    FORMAT_INVALID = "format_invalid"
    TRIAGE_ABANDONED = "triage_abandoned"
    BROKER_UNAVAILABLE = "broker_unavailable"


class Problem(BaseModel):
    """RFC 9457 problem details, plus our stable `code`."""

    model_config = ConfigDict(use_enum_values=True)

    type: str
    title: str
    status: int
    detail: str | None = None
    code: ProblemCode
    triage_id: uuid.UUID | None = None  # with triage_in_progress: the run that's already going


class ApiProblem(Exception):
    """Raised anywhere in request handling; rendered as application/problem+json."""

    def __init__(self, status: int, code: ProblemCode, title: str, detail: str | None = None, **extra):
        super().__init__(f"{status} {code}: {detail or title}")
        self.problem = Problem(type=f"{PROBLEMS_URL}#{code}", title=title, status=status, detail=detail, code=code,
                               **extra)


Severity = Literal["sev1", "sev2", "sev3", "sev4"]
IncidentStatus = Literal["open", "acknowledged", "resolved"]
SectionName = Literal["likely_cause", "blast_radius", "first_steps", "similar_incidents"]


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    service: str = Field(min_length=1, max_length=128)
    severity: Severity
    summary: str = Field(default="", max_length=4000)
    opened_at: datetime | None = Field(default=None, description="When the incident started. Defaults to now.")


class Incident(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    service: str
    severity: Severity
    status: IncidentStatus
    summary: str
    opened_at: datetime
    version: int
    created_at: datetime


class IncidentPage(BaseModel):
    items: list[Incident]
    next_cursor: str | None = Field(description="Pass as `after` for the next page; null on the last page.")


class TriageAccepted(BaseModel):
    triage_id: uuid.UUID
    incident_id: uuid.UUID
    incident_version: int
    stream_url: str


class Citation(BaseModel):
    tag: str = Field(description="The tag as written in the text, e.g. C3.")
    source_type: Literal["runbook"]
    source_id: str = Field(description="The source document, e.g. data/runbooks/ledger-read-only-write-errors.md.")
    chunk_id: uuid.UUID
    chunk_excerpt: str


class BriefSection(BaseModel):
    text: str
    citations: list[Citation]


class BriefSections(BaseModel):
    likely_cause: BriefSection
    blast_radius: BriefSection
    first_steps: BriefSection
    similar_incidents: BriefSection


class TriageUsage(BaseModel):
    prompt_tokens: int
    output_tokens: int
    ttft_ms: int = Field(description="Stream opened to first answer token.")
    total_ms: int


class TriageBrief(BaseModel):
    triage_id: uuid.UUID
    incident_id: uuid.UUID
    incident_version: int
    verdict: Literal["CAUSE_IDENTIFIED", "INSUFFICIENT_EVIDENCE"]
    sections: BriefSections
    model: str
    prompt_version: str
    usage: TriageUsage


# Payloads of the triage stream's events, one model per SSE `event:` name.
class TokenEvent(BaseModel):
    text: str


class CitationEvent(Citation):
    section: SectionName | None = Field(description="The section the tag was written in.")


class SectionCompleteEvent(BaseModel):
    section: SectionName


class ErrorEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    code: ProblemCode
    detail: str
    problems: list[str] = Field(description="With format_invalid: each way the brief broke the section contract.")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class AskCitation(BaseModel):
    tag: str
    chunk_id: uuid.UUID
    document_path: str
    heading_path: str
    text: str


class AskUsage(BaseModel):
    model: str
    prompt_version: str
    prompt_tokens: int
    output_tokens: int
    total_ms: int


class AskResponse(BaseModel):
    answer_id: uuid.UUID
    answer: str
    verdict: Literal["ANSWERED", "INSUFFICIENT_EVIDENCE", "REJECTED"]
    citations: list[AskCitation]
    problems: list[str] = Field(description="Why a REJECTED answer failed the citation contract.")
    usage: AskUsage


REPLAY_MAX = 10_000  # dead letters per replay request


class DlqReplayRequest(BaseModel):
    """Either from_offset and to_offset, or keys."""

    from_offset: int | None = Field(default=None, ge=0, description="First DLQ offset to replay.")
    to_offset: int | None = Field(
        default=None, ge=0, description="Last DLQ offset to replay (inclusive); at most 10000 after from_offset."
    )
    keys: list[str] | None = Field(
        default=None, min_length=1, max_length=100,
        description="Replay every dead letter with one of these message keys (service names).",
    )

    @model_validator(mode="after")
    def one_selection(self) -> "DlqReplayRequest":
        by_range = self.from_offset is not None or self.to_offset is not None
        if by_range == (self.keys is not None):
            raise ValueError("give either from_offset and to_offset, or keys")
        if by_range:
            if self.from_offset is None or self.to_offset is None:
                raise ValueError("a range needs both from_offset and to_offset")
            if not 0 <= self.to_offset - self.from_offset < REPLAY_MAX:
                raise ValueError(f"to_offset must be from_offset to from_offset + {REPLAY_MAX - 1}")
        elif any(not 1 <= len(key) <= 255 for key in self.keys or []):
            raise ValueError("keys must be 1-255 characters")
        return self


class DlqReplayAccepted(BaseModel):
    replayed: int = Field(description="Messages republished to alerts.v1.")
    dlq_offsets: list[int] = Field(description="DLQ offsets of the replayed dead letters, in order.")


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_path: str
    source_type: Literal["runbook", "postmortem"]
    service: str
    heading_path: str
    excerpt: str = Field(description="The chunk's first 280 characters.")
    fts_rank: int | None = Field(default=None, description="Rank in full-text search; null if not in its top 40.")
    fts_score: float | None = Field(default=None, description="ts_rank_cd; higher is better.")
    vector_rank: int | None = Field(default=None, description="Rank in vector search; null if not in its top 40.")
    vector_distance: float | None = Field(default=None, description="Cosine distance; lower is better.")
    rrf_rank: int
    rrf_score: float
    rerank_rank: int | None = None
    rerank_score: float | None = Field(default=None, description="Cross-encoder logit; only the order is meaningful.")


class SearchTimings(BaseModel):
    """Milliseconds per stage. fts and vector overlap (they run concurrently); searches is both."""

    embed: float
    fts: float
    vector: float
    searches: float
    fuse: float
    rerank: float
    total: float


class SearchResponse(BaseModel):
    query: str
    candidates: int = Field(description="Fused chunks the reranker scored.")
    results: list[SearchHit]
    timings_ms: SearchTimings

