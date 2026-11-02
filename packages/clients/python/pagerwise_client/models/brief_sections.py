from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.brief_section import BriefSection


T = TypeVar("T", bound="BriefSections")


@_attrs_define
class BriefSections:
    """
    Attributes:
        likely_cause (BriefSection):
        blast_radius (BriefSection):
        first_steps (BriefSection):
        similar_incidents (BriefSection):
    """

    likely_cause: BriefSection
    blast_radius: BriefSection
    first_steps: BriefSection
    similar_incidents: BriefSection
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        likely_cause = self.likely_cause.to_dict()

        blast_radius = self.blast_radius.to_dict()

        first_steps = self.first_steps.to_dict()

        similar_incidents = self.similar_incidents.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "likely_cause": likely_cause,
                "blast_radius": blast_radius,
                "first_steps": first_steps,
                "similar_incidents": similar_incidents,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.brief_section import BriefSection  # noqa: PLC0415

        d = dict(src_dict)
        likely_cause = BriefSection.from_dict(d.pop("likely_cause"))

        blast_radius = BriefSection.from_dict(d.pop("blast_radius"))

        first_steps = BriefSection.from_dict(d.pop("first_steps"))

        similar_incidents = BriefSection.from_dict(d.pop("similar_incidents"))

        brief_sections = cls(
            likely_cause=likely_cause,
            blast_radius=blast_radius,
            first_steps=first_steps,
            similar_incidents=similar_incidents,
        )

        brief_sections.additional_properties = d
        return brief_sections

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
