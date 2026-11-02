from enum import StrEnum


class DegradedSourceSource(StrEnum):
    DEPLOYS = "deploys"
    POSTMORTEMS = "postmortems"
    RUNBOOKS = "runbooks"

    def __str__(self) -> str:
        return str(self.value)
