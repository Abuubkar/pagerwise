from enum import StrEnum


class ProblemCode(StrEnum):
    FORMAT_INVALID = "format_invalid"
    INVALID_CURSOR = "invalid_cursor"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    NOT_FOUND = "not_found"
    PROMPT_TOO_LONG = "prompt_too_long"
    TRIAGE_ABANDONED = "triage_abandoned"
    TRIAGE_IN_PROGRESS = "triage_in_progress"

    def __str__(self) -> str:
        return str(self.value)
