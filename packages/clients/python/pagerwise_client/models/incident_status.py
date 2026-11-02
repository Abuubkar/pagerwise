from enum import StrEnum


class IncidentStatus(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    OPEN = "open"
    RESOLVED = "resolved"

    def __str__(self) -> str:
        return str(self.value)
