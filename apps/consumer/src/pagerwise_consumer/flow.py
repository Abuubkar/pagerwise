"""When to stop fetching: the consumer's backpressure rule.

Fetching pauses when processing falls behind (too many records queued) or the database is the bottleneck (its pool
nearly all checked out), and resumes only once both have recovered well past the trigger. The gap between the two
thresholds is what stops it pausing and resuming on every poll."""

from dataclasses import dataclass


@dataclass
class Backpressure:
    queue_high: int
    queue_low: int
    pool_high: float
    pool_low: float
    paused: bool = False
    reason: str = ""

    def update(self, queued: int, pool_used: float) -> bool:
        """Returns whether fetching should be paused now. `pool_used` is the checked-out share of the DB pool."""
        if not self.paused:
            if queued >= self.queue_high:
                self.paused, self.reason = True, f"queue {queued} >= {self.queue_high}"
            elif pool_used >= self.pool_high:
                self.paused, self.reason = True, f"db pool {pool_used:.0%} >= {self.pool_high:.0%}"
        elif queued <= self.queue_low and pool_used <= self.pool_low:
            self.paused, self.reason = False, ""
        return self.paused
