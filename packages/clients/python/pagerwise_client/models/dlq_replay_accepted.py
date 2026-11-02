from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="DlqReplayAccepted")


@_attrs_define
class DlqReplayAccepted:
    """
    Attributes:
        replayed (int): Messages republished to alerts.v1.
        dlq_offsets (list[int]): DLQ offsets of the replayed dead letters, in order.
    """

    replayed: int
    dlq_offsets: list[int]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        replayed = self.replayed

        dlq_offsets = self.dlq_offsets

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "replayed": replayed,
                "dlq_offsets": dlq_offsets,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        replayed = d.pop("replayed")

        dlq_offsets = cast(list[int], d.pop("dlq_offsets"))

        dlq_replay_accepted = cls(
            replayed=replayed,
            dlq_offsets=dlq_offsets,
        )

        dlq_replay_accepted.additional_properties = d
        return dlq_replay_accepted

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
