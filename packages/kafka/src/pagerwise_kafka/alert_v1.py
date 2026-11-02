# Generated from contracts/kafka/alert.v1.json by `make codegen`. Do not edit.

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from typing_extensions import TypeAliasType


class Severity(StrEnum):
    critical = 'critical'
    warning = 'warning'
    info = 'info'


LabelsAdditionalProperty = TypeAliasType(
    "LabelsAdditionalProperty", Annotated[str, Field(max_length=512)]
)


class AlertV1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    event_id: Annotated[
        UUID,
        Field(
            description='Unique per event, set by the producer. Consumers deduplicate on it, so a retried send is harmless.'
        ),
    ]
    source: Annotated[
        str,
        Field(
            description='The system that raised the alert, e.g. prometheus or the simulator.',
            max_length=64,
            min_length=1,
        ),
    ]
    service: Annotated[
        str,
        Field(
            description="The service the alert is about. Also the message key, so one service's alerts stay in order.",
            max_length=128,
            min_length=1,
        ),
    ]
    fingerprint: Annotated[
        str,
        Field(
            description='Stable for one alert rule on one target: the same problem firing again has the same fingerprint.',
            max_length=128,
            min_length=1,
        ),
    ]
    severity: Severity
    occurred_at: Annotated[
        AwareDatetime, Field(description='When the alert fired, with a UTC offset.')
    ]
    labels: Annotated[dict[str, LabelsAdditionalProperty], Field(description='Free-form key/value labels from the source, e.g. alertname, instance, region.')] = {

    }
    summary: Annotated[str, Field(max_length=2000, min_length=1)]
