from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.section_name import SectionName

T = TypeVar("T", bound="CitationEvent")


@_attrs_define
class CitationEvent:
    """Data of the stream's `citation` event.

    Attributes:
        tag (str):
        source_type (Literal['runbook']):
        source_id (str):
        chunk_id (UUID):
        chunk_excerpt (str):
        section (None | SectionName): The section the tag was written in.
    """

    tag: str
    source_type: Literal["runbook"]
    source_id: str
    chunk_id: UUID
    chunk_excerpt: str
    section: None | SectionName
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tag = self.tag

        source_type = self.source_type

        source_id = self.source_id

        chunk_id = str(self.chunk_id)

        chunk_excerpt = self.chunk_excerpt

        section: None | str
        if isinstance(self.section, SectionName):
            section = self.section.value
        else:
            section = self.section

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tag": tag,
                "source_type": source_type,
                "source_id": source_id,
                "chunk_id": chunk_id,
                "chunk_excerpt": chunk_excerpt,
                "section": section,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tag = d.pop("tag")

        source_type = cast(Literal["runbook"], d.pop("source_type"))
        if source_type != "runbook":
            raise ValueError(f"source_type must match const 'runbook', got '{source_type}'")

        source_id = d.pop("source_id")

        chunk_id = UUID(d.pop("chunk_id"))

        chunk_excerpt = d.pop("chunk_excerpt")

        def _parse_section(data: object) -> None | SectionName:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                section_type_0 = SectionName(data)

                return section_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SectionName, data)

        section = _parse_section(d.pop("section"))

        citation_event = cls(
            tag=tag,
            source_type=source_type,
            source_id=source_id,
            chunk_id=chunk_id,
            chunk_excerpt=chunk_excerpt,
            section=section,
        )

        citation_event.additional_properties = d
        return citation_event

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
