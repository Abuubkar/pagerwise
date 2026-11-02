from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.problem_code import ProblemCode
from ..types import UNSET, Unset

T = TypeVar("T", bound="Problem")


@_attrs_define
class Problem:
    """RFC 9457 problem details, plus our stable `code`.

    Attributes:
        type_ (str):
        title (str):
        status (int):
        code (ProblemCode):
        detail (None | str | Unset):
        triage_id (None | Unset | UUID): With triage_in_progress, the run that's already going.
    """

    type_: str
    title: str
    status: int
    code: ProblemCode
    detail: None | str | Unset = UNSET
    triage_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        title = self.title

        status = self.status

        code = self.code.value

        detail: None | str | Unset
        if isinstance(self.detail, Unset):
            detail = UNSET
        else:
            detail = self.detail

        triage_id: None | str | Unset
        if isinstance(self.triage_id, Unset):
            triage_id = UNSET
        elif isinstance(self.triage_id, UUID):
            triage_id = str(self.triage_id)
        else:
            triage_id = self.triage_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "title": title,
                "status": status,
                "code": code,
            }
        )
        if detail is not UNSET:
            field_dict["detail"] = detail
        if triage_id is not UNSET:
            field_dict["triage_id"] = triage_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        status = d.pop("status")

        code = ProblemCode(d.pop("code"))

        def _parse_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        detail = _parse_detail(d.pop("detail", UNSET))

        def _parse_triage_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                triage_id_type_0 = UUID(data)

                return triage_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        triage_id = _parse_triage_id(d.pop("triage_id", UNSET))

        problem = cls(
            type_=type_,
            title=title,
            status=status,
            code=code,
            detail=detail,
            triage_id=triage_id,
        )

        problem.additional_properties = d
        return problem

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
