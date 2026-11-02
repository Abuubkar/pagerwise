import uuid
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pagerwise_api import llm, prompts, service
from pagerwise_api.db import get_session

app = FastAPI(title="Pagerwise", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class CitationOut(BaseModel):
    tag: str
    chunk_id: uuid.UUID
    document_path: str
    heading_path: str
    text: str


class Usage(BaseModel):
    model: str
    prompt_version: str
    prompt_tokens: int
    output_tokens: int
    total_ms: int


class AskResponse(BaseModel):
    answer_id: uuid.UUID
    answer: str
    verdict: Literal["ANSWERED", "INSUFFICIENT_EVIDENCE", "REJECTED"]
    citations: list[CitationOut]
    # Why a REJECTED answer failed the citation contract (unknown tags, no citations).
    problems: list[str]
    usage: Usage


@app.post("/v1/ask")
async def ask(body: AskRequest, session: Annotated[AsyncSession, Depends(get_session)]) -> AskResponse:
    try:
        result = await service.ask(session, body.question)
    except llm.PromptTooLong as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ConnectionError as e:  # the ollama client's own error when Ollama isn't running
        raise HTTPException(status_code=503, detail="model server unreachable") from e
    assert result.chat is not None
    return AskResponse(
        answer_id=result.answer_id,
        answer=result.answer,
        verdict=result.verdict,
        citations=[CitationOut(**c.__dict__) for c in result.citations],
        problems=result.problems,
        usage=Usage(
            model=result.chat.model,
            prompt_version=prompts.ASK_PROMPT_VERSION,
            prompt_tokens=result.chat.prompt_tokens,
            output_tokens=result.chat.output_tokens,
            total_ms=result.chat.total_ms,
        ),
    )
