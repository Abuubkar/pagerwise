from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AskUsage")


@_attrs_define
class AskUsage:
    """
    Attributes:
        model (str):
        prompt_version (str):
        prompt_tokens (int):
        output_tokens (int):
        total_ms (int):
    """

    model: str
    prompt_version: str
    prompt_tokens: int
    output_tokens: int
    total_ms: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        model = self.model

        prompt_version = self.prompt_version

        prompt_tokens = self.prompt_tokens

        output_tokens = self.output_tokens

        total_ms = self.total_ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "model": model,
                "prompt_version": prompt_version,
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_ms": total_ms,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model = d.pop("model")

        prompt_version = d.pop("prompt_version")

        prompt_tokens = d.pop("prompt_tokens")

        output_tokens = d.pop("output_tokens")

        total_ms = d.pop("total_ms")

        ask_usage = cls(
            model=model,
            prompt_version=prompt_version,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_ms=total_ms,
        )

        ask_usage.additional_properties = d
        return ask_usage

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
