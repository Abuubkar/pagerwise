from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.triage_brief_verdict import TriageBriefVerdict

if TYPE_CHECKING:
    from ..models.brief_sections import BriefSections
    from ..models.triage_usage import TriageUsage


T = TypeVar("T", bound="TriageBrief")


@_attrs_define
class TriageBrief:
    """Data of the stream's `done` event.

    Attributes:
        triage_id (UUID):
        incident_id (UUID):
        incident_version (int):
        verdict (TriageBriefVerdict):
        sections (BriefSections):
        model (str):
        prompt_version (str):
        usage (TriageUsage):
    """

    triage_id: UUID
    incident_id: UUID
    incident_version: int
    verdict: TriageBriefVerdict
    sections: BriefSections
    model: str
    prompt_version: str
    usage: TriageUsage
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        triage_id = str(self.triage_id)

        incident_id = str(self.incident_id)

        incident_version = self.incident_version

        verdict = self.verdict.value

        sections = self.sections.to_dict()

        model = self.model

        prompt_version = self.prompt_version

        usage = self.usage.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "triage_id": triage_id,
                "incident_id": incident_id,
                "incident_version": incident_version,
                "verdict": verdict,
                "sections": sections,
                "model": model,
                "prompt_version": prompt_version,
                "usage": usage,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.brief_sections import BriefSections  # noqa: PLC0415
        from ..models.triage_usage import TriageUsage  # noqa: PLC0415

        d = dict(src_dict)
        triage_id = UUID(d.pop("triage_id"))

        incident_id = UUID(d.pop("incident_id"))

        incident_version = d.pop("incident_version")

        verdict = TriageBriefVerdict(d.pop("verdict"))

        sections = BriefSections.from_dict(d.pop("sections"))

        model = d.pop("model")

        prompt_version = d.pop("prompt_version")

        usage = TriageUsage.from_dict(d.pop("usage"))

        triage_brief = cls(
            triage_id=triage_id,
            incident_id=incident_id,
            incident_version=incident_version,
            verdict=verdict,
            sections=sections,
            model=model,
            prompt_version=prompt_version,
            usage=usage,
        )

        triage_brief.additional_properties = d
        return triage_brief

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
