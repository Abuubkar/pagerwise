from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.degraded_source_event_source import DegradedSourceEventSource

T = TypeVar("T", bound="DegradedSourceEvent")


@_attrs_define
class DegradedSourceEvent:
    """Data of the stream's `degraded_source` event, sent before the first token.

    Attributes:
        source (DegradedSourceEventSource):
        reason (str): Why it was left out, e.g. 'timed out after 500 ms' or 'HTTP 503'.
    """

    source: DegradedSourceEventSource
    reason: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source = self.source.value

        reason = self.reason

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source": source,
                "reason": reason,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source = DegradedSourceEventSource(d.pop("source"))

        reason = d.pop("reason")

        degraded_source_event = cls(
            source=source,
            reason=reason,
        )

        degraded_source_event.additional_properties = d
        return degraded_source_event

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
