from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.ask_response_verdict import AskResponseVerdict

if TYPE_CHECKING:
    from ..models.ask_citation import AskCitation
    from ..models.ask_usage import AskUsage


T = TypeVar("T", bound="AskResponse")


@_attrs_define
class AskResponse:
    """
    Attributes:
        answer_id (UUID):
        answer (str):
        verdict (AskResponseVerdict):
        citations (list[AskCitation]):
        problems (list[str]): Why a REJECTED answer failed the citation contract.
        usage (AskUsage):
    """

    answer_id: UUID
    answer: str
    verdict: AskResponseVerdict
    citations: list[AskCitation]
    problems: list[str]
    usage: AskUsage
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        answer_id = str(self.answer_id)

        answer = self.answer

        verdict = self.verdict.value

        citations = []
        for citations_item_data in self.citations:
            citations_item = citations_item_data.to_dict()
            citations.append(citations_item)

        problems = self.problems

        usage = self.usage.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "answer_id": answer_id,
                "answer": answer,
                "verdict": verdict,
                "citations": citations,
                "problems": problems,
                "usage": usage,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ask_citation import AskCitation  # noqa: PLC0415
        from ..models.ask_usage import AskUsage  # noqa: PLC0415

        d = dict(src_dict)
        answer_id = UUID(d.pop("answer_id"))

        answer = d.pop("answer")

        verdict = AskResponseVerdict(d.pop("verdict"))

        citations = []
        _citations = d.pop("citations")
        for citations_item_data in _citations:
            citations_item = AskCitation.from_dict(citations_item_data)

            citations.append(citations_item)

        problems = cast(list[str], d.pop("problems"))

        usage = AskUsage.from_dict(d.pop("usage"))

        ask_response = cls(
            answer_id=answer_id,
            answer=answer,
            verdict=verdict,
            citations=citations,
            problems=problems,
            usage=usage,
        )

        ask_response.additional_properties = d
        return ask_response

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
