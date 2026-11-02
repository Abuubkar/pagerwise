from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SearchTimings")


@_attrs_define
class SearchTimings:
    """Milliseconds per stage. fts and vector overlap (they run concurrently); searches is both.

    Attributes:
        embed (float):
        fts (float):
        vector (float):
        searches (float):
        fuse (float):
        rerank (float):
        total (float):
    """

    embed: float
    fts: float
    vector: float
    searches: float
    fuse: float
    rerank: float
    total: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        embed = self.embed

        fts = self.fts

        vector = self.vector

        searches = self.searches

        fuse = self.fuse

        rerank = self.rerank

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "embed": embed,
                "fts": fts,
                "vector": vector,
                "searches": searches,
                "fuse": fuse,
                "rerank": rerank,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        embed = d.pop("embed")

        fts = d.pop("fts")

        vector = d.pop("vector")

        searches = d.pop("searches")

        fuse = d.pop("fuse")

        rerank = d.pop("rerank")

        total = d.pop("total")

        search_timings = cls(
            embed=embed,
            fts=fts,
            vector=vector,
            searches=searches,
            fuse=fuse,
            rerank=rerank,
            total=total,
        )

        search_timings.additional_properties = d
        return search_timings

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
