from hypothesis import given
from hypothesis import strategies as st

from pagerwise_consumer.offsets import OffsetTracker

# Fetched offsets: increasing, with gaps (skipped records). Then the order they finish in, which can be anything.
fetched_and_finish_order = st.lists(st.integers(0, 10_000), min_size=1, max_size=60, unique=True).map(sorted).flatmap(
    lambda offsets: st.tuples(st.just(offsets), st.permutations(offsets))
)


@given(fetched_and_finish_order)
def test_commit_never_passes_a_record_still_in_flight(case):
    fetched, finish_order = case
    tracker = OffsetTracker()
    for offset in fetched:
        tracker.add(offset)

    finished: set[int] = set()
    last = None
    for offset in finish_order:
        tracker.done(offset)
        finished.add(offset)
        committable = tracker.committable()
        pending = [o for o in fetched if o not in finished]
        if pending:
            first_pending = pending[0]
            assert committable is None or committable <= first_pending  # never skips over unfinished work
            done_prefix = [o for o in fetched if o < first_pending]
            assert committable == (done_prefix[-1] + 1 if done_prefix else None)  # ...but goes as far as it safely can
        if last is not None:
            assert committable is not None and committable >= last  # never moves backwards
        last = committable

    assert tracker.committable() == fetched[-1] + 1
    assert tracker.in_flight == 0


def test_discarded_records_dont_block_the_commit():
    """After a seek back, records that will be fetched again are forgotten rather than waited for."""
    tracker = OffsetTracker()
    for offset in (10, 11, 12, 13):
        tracker.add(offset)
    tracker.done(10)
    tracker.discard_from(11)
    assert tracker.committable() == 11
    tracker.add(11)
    tracker.done(11)
    assert tracker.committable() == 12
