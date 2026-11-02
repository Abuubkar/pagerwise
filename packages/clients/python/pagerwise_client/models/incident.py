from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.incident_status import IncidentStatus
from ..models.severity import Severity

T = TypeVar("T", bound="Incident")


@_attrs_define
class Incident:
    """
    Attributes:
        id (UUID):
        title (str):
        service (str):
        severity (Severity):
        status (IncidentStatus):
        summary (str):
        opened_at (datetime.datetime):
        version (int): Goes up on every change; a triage belongs to the version it ran on.
        created_at (datetime.datetime):
    """

    id: UUID
    title: str
    service: str
    severity: Severity
    status: IncidentStatus
    summary: str
    opened_at: datetime.datetime
    version: int
    created_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        title = self.title

        service = self.service

        severity = self.severity.value

        status = self.status.value

        summary = self.summary

        opened_at = self.opened_at.isoformat()

        version = self.version

        created_at = self.created_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "title": title,
                "service": service,
                "severity": severity,
                "status": status,
                "summary": summary,
                "opened_at": opened_at,
                "version": version,
                "created_at": created_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        title = d.pop("title")

        service = d.pop("service")

        severity = Severity(d.pop("severity"))

        status = IncidentStatus(d.pop("status"))

        summary = d.pop("summary")

        opened_at = datetime.datetime.fromisoformat(d.pop("opened_at"))

        version = d.pop("version")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        incident = cls(
            id=id,
            title=title,
            service=service,
            severity=severity,
            status=status,
            summary=summary,
            opened_at=opened_at,
            version=version,
            created_at=created_at,
        )

        incident.additional_properties = d
        return incident

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
