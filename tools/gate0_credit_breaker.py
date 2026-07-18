"""Live 250-normalized-credit breaker for Gate 0 (pre-reg precondition 4).

reports/2026-07-18-gate0-prereg.md precondition 4 / reports/2026-07-13-minimum-north-star-gate-0-design.md:244-246
require a breaker that "halts at 250 normalized credits without relying on
end-of-run arithmetic" -- i.e. it must stop processing THE MOMENT the running
total reaches the limit, not sum a completed log afterward. `run_breaker()`
below enforces that: it never reads past the event that crosses the limit.

This module does not itself know how to convert raw Codex token usage into a
normalized credit delta -- pinning that conversion rate ("25 credits = $1.00")
is a separate, still-open design item (design doc:297-300, HANDOFF.md:298).
Guessing a rate here would risk a real paid run silently under- or
over-tripping, so `iter_normalized_credits()` only accepts events that already
carry a `normalized_credits` number; wire a real token->credit converter in
front of this once that rate is pinned.

Wiring into the launch path: tools/run_gate0_codex.ps1 is deliberately
free-handshake-only today (no `codex exec` path -- design doc:242-243; pinned
by tests/test_run_gate0_codex_launcher.py::test_launcher_is_free_handshake_only_and_fail_closed,
which requires the script to still end in `exit 1`). This breaker is the
component a future paid launcher wraps its streaming `codex exec --json`
output through (one call to `run_breaker()` per turn.completed event,
killing the child process the instant it raises `BreakerTripped`); it is
built and proven correct now, against a synthetic credit stream, so that
wiring is a straight import once the paid launcher exists -- not a new
correctness question at that point.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
from typing import Iterable, Iterator

LIMIT_NORMALIZED_CREDITS = 250


class MalformedCreditStream(Exception):
    """A credit-stream event failed validation. Fail closed: never silently
    treat a malformed event as zero or skip it -- that could let real spend
    cross the limit unaccounted for."""


class BreakerTripped(Exception):
    """Raised by `run_breaker(..., raise_on_trip=True)` the instant the
    running total reaches the limit -- for a live caller that wants to kill
    a child process synchronously rather than inspect a returned dict."""

    def __init__(self, credits_at_trip: float, event_index: int, events_seen: int):
        self.credits_at_trip = credits_at_trip
        self.event_index = event_index
        self.events_seen = events_seen
        super().__init__(
            f"credit breaker tripped at {credits_at_trip} normalized credits "
            f"(event {event_index}, {events_seen} events consumed)")


def validate_event(event: object, index: int) -> float:
    """Extract and validate the normalized-credit delta of one stream event.
    Fail-closed: any shape problem raises MalformedCreditStream immediately."""
    if not isinstance(event, dict):
        raise MalformedCreditStream(f"event_not_object:{index}")
    if "normalized_credits" not in event:
        raise MalformedCreditStream(f"missing_normalized_credits:{index}")
    value = event["normalized_credits"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MalformedCreditStream(f"non_numeric_normalized_credits:{index}")
    if value != value or value in (float("inf"), float("-inf")):  # NaN/inf
        raise MalformedCreditStream(f"non_finite_normalized_credits:{index}")
    if value < 0:
        raise MalformedCreditStream(f"negative_normalized_credits:{index}")
    return float(value)


def load_jsonl(path: Path) -> Iterator[dict]:
    """Fail-closed JSONL reader: a malformed line is never skipped silently
    (matches tools/check_gate0_codex.py's own malformed_jsonl handling)."""
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception as exc:
            raise MalformedCreditStream(f"malformed_jsonl:{line_number}") from exc
        yield event


def run_breaker(events: Iterable[dict], limit: int = LIMIT_NORMALIZED_CREDITS,
                 raise_on_trip: bool = False) -> dict:
    """Consume `events` one at a time, accumulating normalized_credits. The
    INSTANT the running total is >= limit, stop consuming -- any remaining
    events are left unread, which is the whole point: this halts execution
    AT the limit rather than computing sum(all_events) after the fact.

    Returns a dict describing whether it tripped, the exact credits/event
    index/events-seen at the moment of the trip, and how many events (if
    any) were left unconsumed as proof the halt was early, not terminal.
    """
    total = 0.0
    events_seen = 0
    tripped = False
    credits_at_trip = None
    event_index_at_trip = None
    events_in_stream = None

    materialized = list(events) if not hasattr(events, "__next__") else events
    try:
        events_in_stream = len(materialized)  # only known up-front for a list/tuple
    except TypeError:
        events_in_stream = None

    iterator = iter(materialized)
    for index, event in enumerate(iterator):
        total += validate_event(event, index)
        events_seen += 1
        if total >= limit:
            tripped = True
            credits_at_trip = total
            event_index_at_trip = index
            break

    events_after_halt_unconsumed = None
    if tripped and events_in_stream is not None:
        events_after_halt_unconsumed = events_in_stream - events_seen

    if tripped and raise_on_trip:
        raise BreakerTripped(credits_at_trip, event_index_at_trip, events_seen)

    return {
        "tripped": tripped,
        "limit_normalized_credits": limit,
        "credits_at_trip": credits_at_trip,
        "event_index_at_trip": event_index_at_trip,
        "events_seen_before_halt": events_seen,
        "events_in_stream": events_in_stream,
        "unconsumed_events_after_halt": events_after_halt_unconsumed,
        "halted_before_exhausting_stream": bool(
            tripped and events_in_stream is not None and events_seen < events_in_stream),
        "final_total_normalized_credits": total,
    }


def _synthetic_credit_stream() -> list[dict]:
    """Deterministic synthetic stream that crosses LIMIT_NORMALIZED_CREDITS
    partway through, with events left over afterward -- so a dry run can
    demonstrate the breaker halts AT the limit rather than after summing
    the whole stream. 45 events x 6 credits = 270 total > 250; the running
    total first reaches 250 at event index 41 (0-based), i.e. after 42
    events (42 * 6 = 252 >= 250), leaving 3 events unconsumed."""
    return [{"turn": i, "normalized_credits": 6} for i in range(45)]


def dry_run_synthetic(limit: int = LIMIT_NORMALIZED_CREDITS) -> dict:
    """Run the breaker against the synthetic stream and build the
    eval/score_gate0.py-shaped live_credit_breaker artifact. `status` is
    only ever written as 'PASS' if the trip actually happened AND happened
    before the stream was exhausted -- earned by the run, never hand-typed
    (pre-reg precondition 4's tightening: 'the artifact must record an
    actual dry-run TRIP, not a self-declared PASS')."""
    stream = _synthetic_credit_stream()
    stream_bytes = ("\n".join(json.dumps(e) for e in stream) + "\n").encode("utf-8")
    stream_sha256 = hashlib.sha256(stream_bytes).hexdigest()
    trip = run_breaker(stream, limit=limit)

    earned_pass = trip["tripped"] and trip["halted_before_exhausting_stream"]
    artifact = {
        "schema_version": 1,
        "kind": "live_credit_breaker",
        "status": "PASS" if earned_pass else "FAIL",
        "limit_normalized_credits": limit,
        "mode": "dry_run_synthetic",
        "produced_by": "tools/gate0_credit_breaker.py:dry_run_synthetic",
        "produced_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "synthetic_credit_stream": stream,
        "synthetic_credit_stream_sha256": stream_sha256,
        "trip": trip,
        "note": (
            "Dry run with a synthetic credit stream (not a real Codex run): the "
            "breaker's own halting correctness is what this artifact proves, per "
            "reports/2026-07-18-gate0-prereg.md precondition 4's tightening -- an "
            "actual demonstrated TRIP with unconsumed events left behind, not a "
            "self-declared PASS. Wire run_breaker() around the real per-event "
            "Codex token-usage stream once the paid launcher exists; the "
            "token->normalized-credit conversion rate remains a separate open "
            "item (design doc:297-300)."
        ),
    }
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    dry = sub.add_parser("dry-run-synthetic",
                          help="Run the breaker against a built-in synthetic credit stream "
                               "and write the live_credit_breaker artifact.")
    dry.add_argument("--out", type=Path, required=True)
    dry.add_argument("--limit", type=int, default=LIMIT_NORMALIZED_CREDITS)

    live = sub.add_parser("check-stream",
                           help="Run the breaker against a real JSONL credit-delta stream "
                                "(one {\"normalized_credits\": N} object per line).")
    live.add_argument("stream", type=Path)
    live.add_argument("--limit", type=int, default=LIMIT_NORMALIZED_CREDITS)

    args = parser.parse_args()
    if args.command == "dry-run-synthetic":
        artifact = dry_run_synthetic(limit=args.limit)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(artifact, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": artifact["status"], "trip": artifact["trip"],
                          "out": str(args.out)}, sort_keys=True))
        return 0 if artifact["status"] == "PASS" else 1

    # check-stream: fail-closed CLI over a real (or hand-built) JSONL stream.
    try:
        events = list(load_jsonl(args.stream))
    except MalformedCreditStream as exc:
        print(json.dumps({"error": str(exc)}), )
        return 2
    result = run_breaker(events, limit=args.limit)
    print(json.dumps(result, sort_keys=True))
    return 1 if result["tripped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
