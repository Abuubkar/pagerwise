from enum import StrEnum


class SearchHitSourceType(StrEnum):
    POSTMORTEM = "postmortem"
    RUNBOOK = "runbook"

    def __str__(self) -> str:
        return str(self.value)
