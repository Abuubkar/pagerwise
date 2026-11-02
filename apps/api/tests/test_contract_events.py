"""The triage stream's event payloads, as the API builds them, must parse with the client generated from
contracts/openapi.yaml. oasdiff (make contract-check) only compares schemas that operations reference, and SSE
event schemas aren't, so a drift there is caught here instead."""

import json
import uuid

import pytest

from pagerwise_api import schemas
from pagerwise_client import models

CHUNK = uuid.UUID(int=1)


@pytest.mark.parametrize(("payload", "client_model"), [
    (schemas.CitationEvent(tag="C1", source_type="runbook", source_id="data/runbooks/a.md", chunk_id=CHUNK,
                           chunk_excerpt="x", section="likely_cause"), models.CitationEvent),
    (schemas.CitationEvent(tag="C2", source_type="postmortem", source_id="data/corpus/postmortems/b.md",
                           chunk_id=CHUNK, chunk_excerpt="x", section="similar_incidents"), models.CitationEvent),
    (schemas.CitationEvent(tag="C3", source_type="deploy", source_id="dep-0323", chunk_id=None, chunk_excerpt="x",
                           section=None), models.CitationEvent),
    (schemas.DegradedSourceEvent(source="deploys", reason="HTTP 503"), models.DegradedSourceEvent),
    (schemas.TokenEvent(text="## Likely cause"), models.TokenEvent),
    (schemas.SectionCompleteEvent(section="first_steps"), models.SectionCompleteEvent),
    (schemas.ErrorEvent(code=schemas.ProblemCode.TRIAGE_FAILED, detail="boom", problems=[]), models.ErrorEvent),
], ids=["runbook-citation", "postmortem-citation", "deploy-citation", "degraded", "token", "section", "error"])
def test_event_payloads_parse_with_the_generated_client(payload, client_model):
    data = json.loads(payload.model_dump_json())
    assert client_model.from_dict(data).to_dict() == data
