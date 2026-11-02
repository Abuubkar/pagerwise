from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.search_hit_source_type import SearchHitSourceType
from ..types import UNSET, Unset

T = TypeVar("T", bound="SearchHit")


@_attrs_define
class SearchHit:
    """
    Attributes:
        chunk_id (UUID):
        document_path (str):
        source_type (SearchHitSourceType):
        service (str):
        heading_path (str):
        excerpt (str): The chunk's first 280 characters.
        rrf_rank (int):
        rrf_score (float):
        fts_rank (int | None | Unset): Rank in full-text search; null if not in its top 40.
        fts_score (float | None | Unset): ts_rank_cd; higher is better.
        vector_rank (int | None | Unset): Rank in vector search; null if not in its top 40.
        vector_distance (float | None | Unset): Cosine distance; lower is better.
        rerank_rank (int | None | Unset):
        rerank_score (float | None | Unset): Cross-encoder logit; only the order is meaningful.
    """

    chunk_id: UUID
    document_path: str
    source_type: SearchHitSourceType
    service: str
    heading_path: str
    excerpt: str
    rrf_rank: int
    rrf_score: float
    fts_rank: int | None | Unset = UNSET
    fts_score: float | None | Unset = UNSET
    vector_rank: int | None | Unset = UNSET
    vector_distance: float | None | Unset = UNSET
    rerank_rank: int | None | Unset = UNSET
    rerank_score: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        chunk_id = str(self.chunk_id)

        document_path = self.document_path

        source_type = self.source_type.value

        service = self.service

        heading_path = self.heading_path

        excerpt = self.excerpt

        rrf_rank = self.rrf_rank

        rrf_score = self.rrf_score

        fts_rank: int | None | Unset
        if isinstance(self.fts_rank, Unset):
            fts_rank = UNSET
        else:
            fts_rank = self.fts_rank

        fts_score: float | None | Unset
        if isinstance(self.fts_score, Unset):
            fts_score = UNSET
        else:
            fts_score = self.fts_score

        vector_rank: int | None | Unset
        if isinstance(self.vector_rank, Unset):
            vector_rank = UNSET
        else:
            vector_rank = self.vector_rank

        vector_distance: float | None | Unset
        if isinstance(self.vector_distance, Unset):
            vector_distance = UNSET
        else:
            vector_distance = self.vector_distance

        rerank_rank: int | None | Unset
        if isinstance(self.rerank_rank, Unset):
            rerank_rank = UNSET
        else:
            rerank_rank = self.rerank_rank

        rerank_score: float | None | Unset
        if isinstance(self.rerank_score, Unset):
            rerank_score = UNSET
        else:
            rerank_score = self.rerank_score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "chunk_id": chunk_id,
                "document_path": document_path,
                "source_type": source_type,
                "service": service,
                "heading_path": heading_path,
                "excerpt": excerpt,
                "rrf_rank": rrf_rank,
                "rrf_score": rrf_score,
            }
        )
        if fts_rank is not UNSET:
            field_dict["fts_rank"] = fts_rank
        if fts_score is not UNSET:
            field_dict["fts_score"] = fts_score
        if vector_rank is not UNSET:
            field_dict["vector_rank"] = vector_rank
        if vector_distance is not UNSET:
            field_dict["vector_distance"] = vector_distance
        if rerank_rank is not UNSET:
            field_dict["rerank_rank"] = rerank_rank
        if rerank_score is not UNSET:
            field_dict["rerank_score"] = rerank_score

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        chunk_id = UUID(d.pop("chunk_id"))

        document_path = d.pop("document_path")

        source_type = SearchHitSourceType(d.pop("source_type"))

        service = d.pop("service")

        heading_path = d.pop("heading_path")

        excerpt = d.pop("excerpt")

        rrf_rank = d.pop("rrf_rank")

        rrf_score = d.pop("rrf_score")

        def _parse_fts_rank(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fts_rank = _parse_fts_rank(d.pop("fts_rank", UNSET))

        def _parse_fts_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        fts_score = _parse_fts_score(d.pop("fts_score", UNSET))

        def _parse_vector_rank(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        vector_rank = _parse_vector_rank(d.pop("vector_rank", UNSET))

        def _parse_vector_distance(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        vector_distance = _parse_vector_distance(d.pop("vector_distance", UNSET))

        def _parse_rerank_rank(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rerank_rank = _parse_rerank_rank(d.pop("rerank_rank", UNSET))

        def _parse_rerank_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        rerank_score = _parse_rerank_score(d.pop("rerank_score", UNSET))

        search_hit = cls(
            chunk_id=chunk_id,
            document_path=document_path,
            source_type=source_type,
            service=service,
            heading_path=heading_path,
            excerpt=excerpt,
            rrf_rank=rrf_rank,
            rrf_score=rrf_score,
            fts_rank=fts_rank,
            fts_score=fts_score,
            vector_rank=vector_rank,
            vector_distance=vector_distance,
            rerank_rank=rerank_rank,
            rerank_score=rerank_score,
        )

        search_hit.additional_properties = d
        return search_hit

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
