from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DlqReplayRequest")


@_attrs_define
class DlqReplayRequest:
    """Either `from_offset` and `to_offset`, or `keys`.

    Attributes:
        from_offset (int | Unset): First DLQ offset to replay.
        to_offset (int | Unset): Last DLQ offset to replay (inclusive); at most 10000 after from_offset.
        keys (list[str] | Unset): Replay every dead letter with one of these message keys (service names).
    """

    from_offset: int | Unset = UNSET
    to_offset: int | Unset = UNSET
    keys: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from_offset = self.from_offset

        to_offset = self.to_offset

        keys: list[str] | Unset = UNSET
        if not isinstance(self.keys, Unset):
            keys = self.keys

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if from_offset is not UNSET:
            field_dict["from_offset"] = from_offset
        if to_offset is not UNSET:
            field_dict["to_offset"] = to_offset
        if keys is not UNSET:
            field_dict["keys"] = keys

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        from_offset = d.pop("from_offset", UNSET)

        to_offset = d.pop("to_offset", UNSET)

        keys = cast(list[str], d.pop("keys", UNSET))

        dlq_replay_request = cls(
            from_offset=from_offset,
            to_offset=to_offset,
            keys=keys,
        )

        dlq_replay_request.additional_properties = d
        return dlq_replay_request

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
