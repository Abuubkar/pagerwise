from enum import StrEnum


class CitationSourceType(StrEnum):
    DEPLOY = "deploy"
    POSTMORTEM = "postmortem"
    RUNBOOK = "runbook"

    def __str__(self) -> str:
        return str(self.value)
