from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.problem_code import ProblemCode

T = TypeVar("T", bound="ErrorEvent")


@_attrs_define
class ErrorEvent:
    """Data of the stream's `error` event.

    Attributes:
        code (ProblemCode):
        detail (str):
        problems (list[str]): With format_invalid, each way the brief broke the section contract.
    """

    code: ProblemCode
    detail: str
    problems: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code.value

        detail = self.detail

        problems = self.problems

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "detail": detail,
                "problems": problems,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = ProblemCode(d.pop("code"))

        detail = d.pop("detail")

        problems = cast(list[str], d.pop("problems"))

        error_event = cls(
            code=code,
            detail=detail,
            problems=problems,
        )

        error_event.additional_properties = d
        return error_event

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
