from pagerwise_consumer.flow import Backpressure


def controller() -> Backpressure:
    return Backpressure(queue_high=500, queue_low=100, pool_high=0.9, pool_low=0.5)


def test_pauses_at_the_high_mark_and_resumes_only_at_the_low_mark():
    bp = controller()
    assert bp.update(queued=499, pool_used=0) is False
    assert bp.update(queued=500, pool_used=0) is True
    # Draining but still above the low mark: stays paused (no flapping around 500).
    for queued in (450, 300, 101):
        assert bp.update(queued=queued, pool_used=0) is True
    assert bp.update(queued=100, pool_used=0) is False
    # Back below the high mark after resuming: stays resumed.
    assert bp.update(queued=499, pool_used=0) is False


def test_a_saturated_db_pool_pauses_even_with_an_empty_queue():
    bp = controller()
    assert bp.update(queued=0, pool_used=0.85) is False
    assert bp.update(queued=0, pool_used=0.9) is True
    assert "db pool" in bp.reason
    assert bp.update(queued=0, pool_used=0.6) is True  # recovering, not recovered
    assert bp.update(queued=0, pool_used=0.5) is False


def test_resuming_needs_both_queue_and_pool_recovered():
    bp = controller()
    bp.update(queued=600, pool_used=0)
    assert bp.update(queued=50, pool_used=0.7) is True
    assert bp.update(queued=50, pool_used=0.4) is False
