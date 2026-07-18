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
