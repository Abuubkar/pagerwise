"""Request and response models of the REST API. contracts/openapi.yaml is the contract; these must match it
(`make contract-check`)."""

import enum
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
