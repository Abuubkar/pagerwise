import pytest

from pagerwise_kafka import (
    DLQ,
    RETRY_5M,
    RETRY_30S,
    PermanentError,
    TransientError,
    decode_alert,
    header,
    not_before_ms,
    route_failure,
)


def test_transient_failures_walk_the_delay_topics_then_the_dlq():
    headers: list = [("traceparent", b"00-abc"), ("x-tenant", b"acme")]
    hops = []
    topic, partition, offset = "alerts.v1", 7, 1234
    for now in (1_000, 2_000, 3_000):
        target, headers = route_failure(topic, partition, offset, headers, TransientError("timeout"), now_ms=now,
                                        timestamp_ms=now - 500)
        hops.append((target, header(headers, "x-attempt")))
        topic, partition, offset = target, 0, 99  # republished: new coordinates on the retry topic

    assert hops == [(RETRY_30S, "1"), (RETRY_5M, "2"), (DLQ, "3")]
    # The origin and first failure time survive every hop, so the DLQ row points at the original message.
    assert header(headers, "x-original-topic") == "alerts.v1"
    assert header(headers, "x-original-partition") == "7"
    assert header(headers, "x-original-offset") == "1234"
    assert header(headers, "x-first-failed-at") == "1000"
    assert header(headers, "x-original-timestamp") == "500"  # first publish, not the republishes
    assert header(headers, "x-tenant") == "acme"  # headers that aren't ours pass through
    assert header(headers, "traceparent") is None  # except trace context: the republishing producer sets its own
    assert [k for k, _ in headers].count("x-attempt") == 1  # replaced, not appended


def test_a_permanent_failure_goes_straight_to_the_dlq():
    target, headers = route_failure("alerts.v1", 0, 5, [], PermanentError("bad json"), now_ms=1)
    assert target == DLQ
    assert header(headers, "x-attempt") == "1"
    assert header(headers, "x-error-class") == "PermanentError"


def test_not_before_is_publish_time_plus_the_topics_delay():
    delays = {RETRY_30S: 30.0, RETRY_5M: 300.0}
    assert not_before_ms(RETRY_30S, 1_000, delays) == 31_000
    assert not_before_ms(RETRY_5M, 1_000, delays) == 301_000
    assert not_before_ms("alerts.v1", 1_000, delays) == 1_000


@pytest.mark.parametrize("value", [b"not json", b"{}", b'{"event_id": "x"}', None])
def test_malformed_payloads_are_permanent_errors(value):
    with pytest.raises(PermanentError):
        decode_alert(value)
