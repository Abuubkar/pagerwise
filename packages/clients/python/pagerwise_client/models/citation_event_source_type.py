from enum import StrEnum


class CitationEventSourceType(StrEnum):
    DEPLOY = "deploy"
    POSTMORTEM = "postmortem"
    RUNBOOK = "runbook"

    def __str__(self) -> str:
        return str(self.value)
