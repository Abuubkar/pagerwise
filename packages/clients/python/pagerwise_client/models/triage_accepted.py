from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TriageAccepted")


@_attrs_define
class TriageAccepted:
    """
    Attributes:
        triage_id (UUID):
        incident_id (UUID):
        incident_version (int):
        stream_url (str):
    """

    triage_id: UUID
    incident_id: UUID
    incident_version: int
    stream_url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        triage_id = str(self.triage_id)

        incident_id = str(self.incident_id)

        incident_version = self.incident_version

        stream_url = self.stream_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "triage_id": triage_id,
                "incident_id": incident_id,
                "incident_version": incident_version,
                "stream_url": stream_url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        triage_id = UUID(d.pop("triage_id"))

        incident_id = UUID(d.pop("incident_id"))

        incident_version = d.pop("incident_version")

        stream_url = d.pop("stream_url")

        triage_accepted = cls(
            triage_id=triage_id,
            incident_id=incident_id,
            incident_version=incident_version,
            stream_url=stream_url,
        )

        triage_accepted.additional_properties = d
        return triage_accepted

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
