from enum import StrEnum


class SectionName(StrEnum):
    BLAST_RADIUS = "blast_radius"
    FIRST_STEPS = "first_steps"
    LIKELY_CAUSE = "likely_cause"
    SIMILAR_INCIDENTS = "similar_incidents"

    def __str__(self) -> str:
        return str(self.value)
