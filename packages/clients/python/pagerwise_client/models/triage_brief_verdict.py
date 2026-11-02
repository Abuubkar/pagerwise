from enum import StrEnum


class TriageBriefVerdict(StrEnum):
    CAUSE_IDENTIFIED = "CAUSE_IDENTIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    def __str__(self) -> str:
        return str(self.value)
