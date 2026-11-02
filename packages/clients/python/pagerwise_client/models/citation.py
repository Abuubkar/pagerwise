from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.citation_source_type import CitationSourceType

T = TypeVar("T", bound="Citation")


@_attrs_define
class Citation:
    """
    Attributes:
        tag (str): The tag as written in the text, e.g. C3.
        source_type (CitationSourceType):
        source_id (str): The source: a document path (runbook, postmortem) or a deploy id.
        chunk_id (None | UUID): The cited chunk of the document; null for a deploy.
        chunk_excerpt (str):
    """

    tag: str
    source_type: CitationSourceType
    source_id: str
    chunk_id: None | UUID
    chunk_excerpt: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tag = self.tag

        source_type = self.source_type.value

        source_id = self.source_id

        chunk_id: None | str
        if isinstance(self.chunk_id, UUID):
            chunk_id = str(self.chunk_id)
        else:
            chunk_id = self.chunk_id

        chunk_excerpt = self.chunk_excerpt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tag": tag,
                "source_type": source_type,
                "source_id": source_id,
                "chunk_id": chunk_id,
                "chunk_excerpt": chunk_excerpt,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tag = d.pop("tag")

        source_type = CitationSourceType(d.pop("source_type"))

        source_id = d.pop("source_id")

        def _parse_chunk_id(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                chunk_id_type_0 = UUID(data)

                return chunk_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        chunk_id = _parse_chunk_id(d.pop("chunk_id"))

        chunk_excerpt = d.pop("chunk_excerpt")

        citation = cls(
            tag=tag,
            source_type=source_type,
            source_id=source_id,
            chunk_id=chunk_id,
            chunk_excerpt=chunk_excerpt,
        )

        citation.additional_properties = d
        return citation

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
