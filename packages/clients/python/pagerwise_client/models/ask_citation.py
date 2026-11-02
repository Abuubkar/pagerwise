from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AskCitation")


@_attrs_define
class AskCitation:
    """
    Attributes:
        tag (str):
        chunk_id (UUID):
        document_path (str):
        heading_path (str):
        text (str):
    """

    tag: str
    chunk_id: UUID
    document_path: str
    heading_path: str
    text: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tag = self.tag

        chunk_id = str(self.chunk_id)

        document_path = self.document_path

        heading_path = self.heading_path

        text = self.text

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tag": tag,
                "chunk_id": chunk_id,
                "document_path": document_path,
                "heading_path": heading_path,
                "text": text,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tag = d.pop("tag")

        chunk_id = UUID(d.pop("chunk_id"))

        document_path = d.pop("document_path")

        heading_path = d.pop("heading_path")

        text = d.pop("text")

        ask_citation = cls(
            tag=tag,
            chunk_id=chunk_id,
            document_path=document_path,
            heading_path=heading_path,
            text=text,
        )

        ask_citation.additional_properties = d
        return ask_citation

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
