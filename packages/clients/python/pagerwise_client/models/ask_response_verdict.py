from enum import StrEnum


class AskResponseVerdict(StrEnum):
    ANSWERED = "ANSWERED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"

    def __str__(self) -> str:
        return str(self.value)
