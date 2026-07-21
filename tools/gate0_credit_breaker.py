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
over-tripping, so `validate_event()` only accepts events that already
carry a `normalized_credits` number; wire a real token->credit converter in
front of this once that rate is pinned (for the now-pinned model gpt-5.6-sol).

Wiring into the launch path: tools/run_gate0_codex.ps1 is deliberately
free-handshake-only today (no `codex exec` path -- design doc:242-243; pinned
by tests/test_run_gate0_codex_launcher.py::test_launcher_is_free_handshake_only_and_fail_closed,
which requires the script to still end in `exit 1`). This breaker is the
component a future paid launcher wraps its streaming `codex exec --json`
output through. THE KILL CONTRACT (PR #118 breaker review, MINOR 2): the
wired caller must feed `run_breaker(raise_on_trip=True)` an ITERATOR pulled
lazily from the live stream (never a buffered/materialized source -- see the
MAJOR-1 note at the iteration site below) and must kill the codex child the
instant run_breaker raises ANY breaker exception -- `BreakerTripped` OR
`MalformedCreditStream`. Catching only BreakerTripped is fail-open: a
malformed or stalled stream crashes the accountant while the child keeps
spending. The wired path must also arm the stall backstop
(stall_timeout_s=STALL_TIMEOUT_S, pre-registered 300 s: no event for that
long raises MalformedCreditStream -> child killed), because a silently
stalled stream otherwise blocks the accountant forever while the child
spends (review MINOR 3a).

Float-boundary note (review MINOR 4, bounded and accepted): credits
accumulate in floats, so a stream whose exact-math running total lands
precisely on the limit can sit epsilon under it and trip one event later.
The overshoot is bounded by a single event's delta (about one turn's
credits) -- pre-registered as acceptable; the wired spec inherits this line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import queue
import threading
from pathlib import Path
from typing import Iterable, Iterator

LIMIT_NORMALIZED_CREDITS = 250
# Pre-registered wired-path stall backstop (PR #118 breaker review MINOR 3a): if the live stream
# produces no event for this many wall-clock seconds, the breaker raises MalformedCreditStream
# ("stall_timeout:*") and the wired caller kills the child. The paid launcher must pass
# stall_timeout_s=STALL_TIMEOUT_S (or a pre-registered stricter value); run_breaker()'s default of
# None is only for in-memory/sized sources, where a stall is impossible and where the strict
# pull-on-demand guarantee (see the MAJOR-1 regression tests) must hold with zero threading.
STALL_TIMEOUT_S = 300


class MalformedCreditStream(Exception):
    """A credit-stream event failed validation. Fail closed: never silently
    treat a malformed event as zero or skip it -- that could let real spend
    cross the limit unaccounted for."""


class BreakerTripped(Exception):
    """Raised by `run_breaker(..., raise_on_trip=True)` the instant the
    running total reaches the limit -- for a live caller that wants to kill
    a child process synchronously rather than inspect a returned dict.

    Kill contract: the wired caller must treat BOTH this exception AND
    MalformedCreditStream as kill-the-child signals. Either one means the
    accountant can no longer vouch for spend staying under the limit."""

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


def _timed_iter(iterator: Iterator[dict], stall_timeout_s: float) -> Iterator[dict]:
    """Yield from `iterator`, raising MalformedCreditStream('stall_timeout:<index>')
    if the next event takes more than stall_timeout_s wall-clock seconds to
    arrive (review MINOR 3a: an untimed blocking pull is fail-open in the wired
    system -- the child keeps spending while the accountant waits forever).

    Implementation note: a blocking next() cannot be interrupted portably, so
    the pull runs on a daemon thread feeding a 1-slot queue. That means the
    source may be pulled AT MOST ONE event ahead of the consumer -- reading one
    extra usage event from a pipe costs nothing and cannot spend; the strict
    zero-read-ahead guarantee (MAJOR-1 regression tests) applies to the untimed
    path, and the wired-path halt evidence comes from emitter-side tail + child
    termination (PR #118 precondition-4 checklist item 4c), not from read
    counts. After a stall or trip the daemon thread may linger blocked on its
    final put; it holds no resources and dies with the process."""
    channel: queue.Queue = queue.Queue(maxsize=1)

    def _pull() -> None:
        try:
            for item in iterator:
                channel.put(("event", item))
            channel.put(("done", None))
        except BaseException as exc:  # propagate source failures to the consumer
            channel.put(("error", exc))

    threading.Thread(target=_pull, daemon=True).start()
    index = 0
    while True:
        try:
            kind, payload = channel.get(timeout=stall_timeout_s)
        except queue.Empty:
            raise MalformedCreditStream(f"stall_timeout:{index}") from None
        if kind == "done":
            return
        if kind == "error":
            raise payload
        yield payload
        index += 1


def run_breaker(events: Iterable[dict], limit: int = LIMIT_NORMALIZED_CREDITS,
                 raise_on_trip: bool = False,
                 stall_timeout_s: float | None = None) -> dict:
    """Consume `events` one at a time, accumulating normalized_credits. The
    INSTANT the running total is >= limit, stop consuming -- any remaining
    events are left unread, which is the whole point: this halts execution
    AT the limit rather than computing sum(all_events) after the fact.

    `stall_timeout_s`: the wired paid path MUST pass STALL_TIMEOUT_S (300 s,
    pre-registered) or a stricter pre-registered value; None (default) is only
    for in-memory/sized sources where a stall is impossible.

    Returns a dict describing whether it tripped, the exact credits/event
    index/events-seen at the moment of the trip, and -- for sized sequences
    only -- how many events were left unconsumed as proof the halt was early.
    `halted_before_exhausting_stream` is only ever True when the source's size
    is known WITHOUT consuming it (list/tuple): a receipt must never claim an
    early halt it cannot prove (review MAJOR 1).
    """
    total = 0.0
    events_seen = 0
    tripped = False
    credits_at_trip = None
    event_index_at_trip = None

    # Review MAJOR 1 (PR #118): NEVER list()-materialize the source. iter() consumes lazily for
    # EVERY source kind (iterators, generators, and iterable-but-not-iterator wrappers alike);
    # the only thing materializing bought was len(), which is recoverable from already-sized
    # sequences alone. Draining a live source up front would turn the receipt into post-hoc
    # arithmetic wearing a live-halt claim -- the exact evidence class precondition 4 forbids.
    sized = isinstance(events, (list, tuple))
    events_in_stream = len(events) if sized else None
    iterator = iter(events)
    if stall_timeout_s is not None and not sized:
        iterator = _timed_iter(iterator, stall_timeout_s)

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
        "source_kind": "sized_sequence" if sized else "lazy_iterator",
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
    # Deterministic by design (PR #118 pins review MINOR 1): no wall-clock timestamp in the hashed
    # content -- the artifact's bytes are a pure function of this module's code, so the pinned
    # sha256 reproduces from any checkout on any platform (writing is LF-forced in main() for the
    # same reason). Provenance/when lives in git history + the banked report, not in the bytes.
    artifact = {
        "schema_version": 1,
        "kind": "live_credit_breaker",
        "status": "PASS" if earned_pass else "FAIL",
        "limit_normalized_credits": limit,
        "mode": "dry_run_synthetic",
        "produced_by": "tools/gate0_credit_breaker.py:dry_run_synthetic",
        "synthetic_credit_stream": stream,
        "synthetic_credit_stream_sha256": stream_sha256,
        "trip": trip,
        "note": (
            "Dry run with a synthetic credit stream (not a real Codex run): this "
            "artifact proves DETECTOR correctness only, per reports/2026-07-18-"
            "gate0-prereg.md precondition 4's tightening -- an actual demonstrated "
            "TRIP with a counted unconsumed tail (sized source), not a self-"
            "declared PASS. It does not prove halting of paid consumption "
            "(unread != unspent): precondition 4 status is COMPONENT MET -- "
            "WIRING PENDING, and the paid launch additionally requires the "
            "4a-4d wired-path checklist banked on PR #118 (token->credit rate "
            "pinned for gpt-5.6-sol; iterator-fed run_breaker(raise_on_trip="
            "True) killing the child on ANY breaker exception; a wired-path "
            "TRIP receipt against a zero-spend stub emitter with child-"
            "termination evidence; the pre-registered 300 s stall backstop)."
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
        # newline="\n" is load-bearing: default newline translation would write CRLF on Windows,
        # making the artifact's sha256 platform-dependent (pins review MINOR 1).
        args.out.write_text(json.dumps(artifact, indent=2, sort_keys=False) + "\n",
                            encoding="utf-8", newline="\n")
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
