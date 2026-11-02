from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.severity import Severity
from ..types import UNSET, Unset

T = TypeVar("T", bound="IncidentCreate")


@_attrs_define
class IncidentCreate:
    """
    Attributes:
        title (str):
        service (str):
        severity (Severity):
        summary (str | Unset):  Default: ''.
        opened_at (datetime.datetime | None | Unset): When the incident started. Defaults to now.
    """

    title: str
    service: str
    severity: Severity
    summary: str | Unset = ""
    opened_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        title = self.title

        service = self.service

        severity = self.severity.value

        summary = self.summary

        opened_at: None | str | Unset
        if isinstance(self.opened_at, Unset):
            opened_at = UNSET
        elif isinstance(self.opened_at, datetime.datetime):
            opened_at = self.opened_at.isoformat()
        else:
            opened_at = self.opened_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "title": title,
                "service": service,
                "severity": severity,
            }
        )
        if summary is not UNSET:
            field_dict["summary"] = summary
        if opened_at is not UNSET:
            field_dict["opened_at"] = opened_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        title = d.pop("title")

        service = d.pop("service")

        severity = Severity(d.pop("severity"))

        summary = d.pop("summary", UNSET)

        def _parse_opened_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                opened_at_type_0 = datetime.datetime.fromisoformat(data)

                return opened_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        opened_at = _parse_opened_at(d.pop("opened_at", UNSET))

        incident_create = cls(
            title=title,
            service=service,
            severity=severity,
            summary=summary,
            opened_at=opened_at,
        )

        incident_create.additional_properties = d
        return incident_create

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
