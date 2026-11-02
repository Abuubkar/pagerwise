from enum import StrEnum


class Severity(StrEnum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"

    def __str__(self) -> str:
        return str(self.value)
