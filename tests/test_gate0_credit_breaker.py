import hashlib
import json

import pytest

from tools.gate0_credit_breaker import (
    BreakerTripped,
    MalformedCreditStream,
    dry_run_synthetic,
    load_jsonl,
    run_breaker,
    validate_event,
)


def _events(*credits):
    return [{"normalized_credits": c} for c in credits]


def test_breaker_does_not_trip_under_limit():
    result = run_breaker(_events(10, 20, 30), limit=250)
    assert result["tripped"] is False
    assert result["final_total_normalized_credits"] == 60
    assert result["events_seen_before_halt"] == 3
    assert result["unconsumed_events_after_halt"] is None


def test_breaker_trips_at_exactly_the_limit():
    # 25 events of 10 credits: running total hits exactly 250 at the 25th event (index 24).
    result = run_breaker(_events(*([10] * 25)), limit=250)
    assert result["tripped"] is True
    assert result["credits_at_trip"] == 250
    assert result["event_index_at_trip"] == 24
    assert result["events_seen_before_halt"] == 25


def test_breaker_halts_before_reading_remaining_events_not_post_hoc_sum():
    # 45 events of 6 credits (270 total if fully consumed). The instant the running total is >=
    # 250 (event 42, total 252) the breaker must stop -- proving it halts AT the limit rather than
    # summing the whole stream after the fact. Events 43-45 must be left unconsumed.
    result = run_breaker(_events(*([6] * 45)), limit=250)
    assert result["tripped"] is True
    assert result["credits_at_trip"] == 252
    assert result["events_seen_before_halt"] == 42
    assert result["events_in_stream"] == 45
    assert result["unconsumed_events_after_halt"] == 3
    assert result["halted_before_exhausting_stream"] is True


def test_breaker_never_overshoots_by_more_than_one_event():
    # However the deltas are shaped, the trip must fire on the FIRST event that crosses the limit,
    # never later -- confirms there is no buffering/batch-then-check behavior hiding a later trip.
    result = run_breaker(_events(100, 100, 100), limit=250)
    assert result["tripped"] is True
    assert result["credits_at_trip"] == 300
    assert result["event_index_at_trip"] == 2
    assert result["events_seen_before_halt"] == 3


def test_breaker_halts_early_on_a_true_generator_never_materializing_the_rest():
    # A live stream (e.g. piped subprocess output) must not be read past the trip point. Model that
    # here with a generator that raises if pulled beyond the expected halt index.
    def poisoned_stream():
        for i in range(45):
            if i > 41:
                raise AssertionError("breaker read past the event that tripped it")
            yield {"normalized_credits": 6}

    result = run_breaker(poisoned_stream(), limit=250)
    assert result["tripped"] is True
    assert result["events_seen_before_halt"] == 42
    # A true (unsized) generator cannot report events_in_stream up front.
    assert result["events_in_stream"] is None


class _CountingIterableSource:
    """Iterable but NOT an iterator (__iter__ without __next__) -- the PR #118 breaker review
    MAJOR 1 repro shape: an easy wrapper class for a future paid launcher to hand over."""

    def __init__(self, n):
        self.n = n
        self.pulled = 0

    def __iter__(self):
        def _gen():
            for i in range(self.n):
                self.pulled += 1
                yield {"turn": i, "normalized_credits": 6}
        return _gen()


def test_iterable_but_not_iterator_source_is_never_materialized():
    # PR #118 breaker review MAJOR 1: pre-fix, `list(events) if not hasattr(events, "__next__")`
    # silently DRAINED any iterable-not-iterator source in full (45/45 pulled) before trip logic
    # ran, then issued a receipt claiming halted_before_exhausting_stream=True with a 3-event
    # "unconsumed tail" -- post-hoc arithmetic wearing a live-halt claim. Post-fix, iter() pulls
    # lazily for every source kind: the source must have exactly 3 events never pulled.
    source = _CountingIterableSource(45)
    result = run_breaker(source, limit=250)
    assert result["tripped"] is True
    assert result["credits_at_trip"] == 252
    assert result["events_seen_before_halt"] == 42
    assert source.pulled == 42, "source was materialized: events pulled past the trip point"
    assert result["source_kind"] == "lazy_iterator"
    # An unsized source can never claim a counted tail or an early-halt boolean it cannot prove.
    assert result["events_in_stream"] is None
    assert result["unconsumed_events_after_halt"] is None
    assert result["halted_before_exhausting_stream"] is False


def test_sized_sequence_tail_claim_requires_no_consumption_to_prove():
    # The counted-tail/early-halt claim survives ONLY where it is honest: list/tuple sources,
    # whose len() is known without consuming anything.
    result = run_breaker(tuple(_events(*([6] * 45))), limit=250)
    assert result["source_kind"] == "sized_sequence"
    assert result["events_in_stream"] == 45
    assert result["unconsumed_events_after_halt"] == 3
    assert result["halted_before_exhausting_stream"] is True


def test_stall_timeout_fails_closed():
    # PR #118 breaker review MINOR 3a: a silent stream must not block the accountant forever
    # while the child spends. With the backstop armed, a stall raises MalformedCreditStream
    # (a kill-the-child exception per the wiring contract), never a hang.
    import time

    def stalling_stream():
        yield {"normalized_credits": 1}
        time.sleep(2)
        yield {"normalized_credits": 1}

    with pytest.raises(MalformedCreditStream, match="stall_timeout:1"):
        run_breaker(stalling_stream(), limit=250, stall_timeout_s=0.2)


def test_timed_path_still_trips_and_propagates_malformed_events():
    def stream_45x6():
        for i in range(45):
            yield {"normalized_credits": 6}

    result = run_breaker(stream_45x6(), limit=250, stall_timeout_s=5)
    assert result["tripped"] is True
    assert result["credits_at_trip"] == 252

    def malformed_second():
        yield {"normalized_credits": 6}
        yield {"bad": True}

    with pytest.raises(MalformedCreditStream, match="missing_normalized_credits:1"):
        run_breaker(malformed_second(), limit=250, stall_timeout_s=5)


def test_starting_credits_defaults_to_zero_and_preserves_existing_behavior():
    result = run_breaker(_events(10, 20, 30), limit=250, starting_credits=0.0)
    assert result["tripped"] is False
    assert result["final_total_normalized_credits"] == 60


def test_starting_credits_carries_over_from_a_prior_arm():
    # PR #122 coordinator M4: the combined ceiling across two arms is enforced by seeding the
    # second arm's breaker with the first arm's already-consumed total.
    result = run_breaker(_events(5, 5), limit=250, starting_credits=246)
    assert result["tripped"] is True
    assert result["credits_at_trip"] == 251
    assert result["event_index_at_trip"] == 0
    assert result["events_seen_before_halt"] == 1


def test_starting_credits_already_at_limit_trips_before_reading_any_event():
    def poisoned_stream():
        raise AssertionError("must not pull from the stream when already over budget")
        yield  # pragma: no cover

    result = run_breaker(poisoned_stream(), limit=250, starting_credits=250)
    assert result["tripped"] is True
    assert result["credits_at_trip"] == 250
    assert result["event_index_at_trip"] == -1
    assert result["events_seen_before_halt"] == 0


def test_starting_credits_over_limit_raises_immediately_with_raise_on_trip():
    def poisoned_stream():
        raise AssertionError("must not pull from the stream when already over budget")
        yield  # pragma: no cover

    with pytest.raises(BreakerTripped) as excinfo:
        run_breaker(poisoned_stream(), limit=250, starting_credits=300, raise_on_trip=True)
    assert excinfo.value.credits_at_trip == 300
    assert excinfo.value.event_index == -1


@pytest.mark.parametrize("bad_value", [-1, "10", True, float("nan")])
def test_starting_credits_fails_closed_on_invalid_value(bad_value):
    with pytest.raises(MalformedCreditStream, match="invalid_starting_credits"):
        run_breaker(_events(1), limit=250, starting_credits=bad_value)


def test_raise_on_trip_carries_the_same_evidence():
    with pytest.raises(BreakerTripped) as excinfo:
        run_breaker(_events(*([10] * 26)), limit=250, raise_on_trip=True)
    assert excinfo.value.credits_at_trip == 250
    assert excinfo.value.event_index == 24
    assert excinfo.value.events_seen == 25


@pytest.mark.parametrize("bad_event", [
    {},
    {"normalized_credits": "ten"},
    {"normalized_credits": True},
    {"normalized_credits": -1},
    {"normalized_credits": float("nan")},
    {"normalized_credits": float("inf")},
    "not-a-dict",
    None,
])
def test_breaker_fails_closed_on_malformed_credit_stream(bad_event):
    with pytest.raises(MalformedCreditStream):
        run_breaker([{"normalized_credits": 10}, bad_event, {"normalized_credits": 10}], limit=250)


def test_validate_event_error_names_the_index():
    with pytest.raises(MalformedCreditStream, match="missing_normalized_credits:3"):
        validate_event({}, 3)


def test_malformed_stream_halts_before_the_limit_is_reached_too():
    # Fail-closed must apply even when the malformed event arrives before any trip would have
    # happened -- never silently treat it as zero and keep going.
    with pytest.raises(MalformedCreditStream):
        run_breaker(_events(1, 1) + [{"bad": True}], limit=250)


def test_load_jsonl_round_trips_valid_stream(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_text('{"normalized_credits": 5}\n{"normalized_credits": 7}\n', encoding="utf-8")
    events = list(load_jsonl(path))
    assert events == [{"normalized_credits": 5}, {"normalized_credits": 7}]


def test_load_jsonl_fails_closed_on_malformed_json_line(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_text('{"normalized_credits": 5}\nnot json\n', encoding="utf-8")
    with pytest.raises(MalformedCreditStream, match="malformed_jsonl:2"):
        list(load_jsonl(path))


def test_dry_run_synthetic_produces_an_earned_pass_not_a_self_declared_one():
    artifact = dry_run_synthetic()
    assert artifact["schema_version"] == 1
    assert artifact["kind"] == "live_credit_breaker"
    assert artifact["limit_normalized_credits"] == 250
    assert artifact["status"] == "PASS"
    # The tightening this exists for: PASS must be backed by trip evidence, not asserted.
    assert artifact["trip"]["tripped"] is True
    assert artifact["trip"]["halted_before_exhausting_stream"] is True
    assert artifact["trip"]["unconsumed_events_after_halt"] > 0
    stream_bytes = ("\n".join(json.dumps(e) for e in artifact["synthetic_credit_stream"]) + "\n").encode("utf-8")
    assert artifact["synthetic_credit_stream_sha256"] == hashlib.sha256(stream_bytes).hexdigest()


def test_dry_run_synthetic_would_fail_closed_if_the_stream_never_tripped():
    # A stream that never reaches the limit must never be reported as an earned PASS.
    artifact = dry_run_synthetic(limit=10_000)
    assert artifact["trip"]["tripped"] is False
    assert artifact["status"] == "FAIL"
