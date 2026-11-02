"""Which offset of a partition is safe to commit.

Kafka resumes a partition from its committed offset, so committing offset N says "everything before N is done".
Records can finish out of order, and offsets can have gaps (records skipped after a seek), so the safe commit is the
first record still in flight, or one past the last record if none is."""


class OffsetTracker:
    """One per assigned partition. Offsets are added in the order they were fetched."""

    def __init__(self) -> None:
        self._in_flight: dict[int, bool] = {}  # offset -> done; insertion order is fetch order
        self._next_commit: int | None = None

    def add(self, offset: int) -> None:
        self._in_flight[offset] = False

    def done(self, offset: int) -> None:
        self._in_flight[offset] = True
        # Everything at the front that's done is safe to commit past.
        while self._in_flight:
            first = next(iter(self._in_flight))
            if not self._in_flight[first]:
                break
            del self._in_flight[first]
            self._next_commit = first + 1

    def discard_from(self, offset: int) -> None:
        """Forget records at or after `offset` that will be fetched again (the partition was seeked back)."""
        for o in [o for o in self._in_flight if o >= offset]:
            del self._in_flight[o]

    def committable(self) -> int | None:
        """The offset to commit (the next record to read), or None if nothing has finished yet."""
        return self._next_commit

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)
