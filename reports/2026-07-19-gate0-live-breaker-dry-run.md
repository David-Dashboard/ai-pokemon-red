# Gate 0 live credit breaker -- dry-run TRIP receipt (precondition 4) -- 2026-07-19

*(Revised 2026-07-21 after the PR #118 adversarial reviews: breaker MAJOR 1 fixed -- iter()-always,
never materialize a live source; the artifact is now DETERMINISTIC -- no wall-clock timestamp,
LF-forced write -- so its hash reproduces from the committed tool on any platform; kill contract
extended to both breaker exceptions; 300 s stall backstop added; precondition-4 status adopted as
COMPONENT MET -- WIRING PENDING per the reviewer's ruling, see the PR #118 body's 4a-4d checklist.)*

`runs/` is gitignored (`.gitignore:27`), so the artifact this report documents lives only on the
producing machine at `runs/gate0_live_breaker/live_breaker_dry_run_trip.json` -- this report is the
committed evidence, per the pre-reg's own convention for `runs/` artifacts (e.g.
`reports/2026-07-14-gate0-readiness.md` citing `runs/gate0_readiness_2026-07-14/...` by hash rather
than committing it). Unlike an observed run receipt, this artifact is deliberately REGENERABLE:
its bytes are a pure function of `tools/gate0_credit_breaker.py`'s committed code (no timestamp,
LF-forced), so `uv run --frozen python tools/gate0_credit_breaker.py dry-run-synthetic --out <path>`
reproduces the pinned hash byte-exactly on any platform (verified: two consecutive regenerations on
2026-07-21 produced identical hashes; zero CR bytes in the output).

## What this closes

`reports/2026-07-18-gate0-prereg.md` precondition 4: "Live breaker dry-run TRIP receipt." The design
doc requires "a live breaker that halts at 250 normalized credits without relying on end-of-run
arithmetic" (`reports/2026-07-13-minimum-north-star-gate-0-design.md:244-246`); the pre-reg's
tightening over the scorer's mechanical check (`eval/score_gate0.py`'s `live_breaker` requirement,
`kind=live_credit_breaker`, `status=PASS`, `limit=250`) is that the artifact "must record an actual
dry-run TRIP ... not merely a self-declared PASS status" (`reports/2026-07-18-gate0-prereg.md` row 4).

## What was built

`tools/gate0_credit_breaker.py`:
- `run_breaker(events, limit=250, stall_timeout_s=None)` -- consumes a stream of
  `{"normalized_credits": N}` events and stops accumulating THE INSTANT the running total is
  `>= limit`. It never processes events past the one that crosses the limit -- that is the actual
  halting property the design doc asks for, not a `sum()` computed after reading everything.
  **Review MAJOR 1 fix (2026-07-21):** the source is consumed via `iter()` for EVERY source kind --
  never `list()`-materialized -- so an iterable-but-not-iterator wrapper is pulled lazily too
  (regression-tested: 45-event source, trip at event 42, exactly 3 events never pulled from the
  source). `halted_before_exhausting_stream`/`unconsumed_events_after_halt` are only ever
  claimed for sized sequences (list/tuple), whose length is knowable without consumption -- the
  receipt never claims an early halt it cannot prove; `source_kind` records which case ran.
- `validate_event()` / `load_jsonl()` -- fail closed on a malformed stream (missing key, non-numeric,
  bool-as-numeric, NaN/inf, negative): raise `MalformedCreditStream` immediately rather than treating
  a bad event as zero and continuing.
- **Stall backstop (review MINOR 3a):** `stall_timeout_s` arms a wall-clock no-event timeout --
  no event for that long raises `MalformedCreditStream("stall_timeout:<index>")` instead of
  blocking forever while the child spends. Pre-registered wired-path value: `STALL_TIMEOUT_S = 300`
  seconds; the paid launcher must pass it (the `None` default is only for in-memory/sized sources,
  where a stall is impossible and strict zero-read-ahead must hold without threading).
- **Float-boundary note (review MINOR 4, bounded, accepted):** float accumulation can land epsilon
  under the limit and trip one event later; the overshoot is bounded by one event's delta.
- `dry_run_synthetic()` -- builds a deterministic synthetic 45-event stream (6 normalized credits
  each, 270 total), runs it through `run_breaker()`, and only ever writes `status: "PASS"` into the
  artifact if the run *actually* tripped *and* halted before exhausting the stream -- both computed
  from the real `run_breaker()` return value, never hand-typed. The artifact carries no timestamp
  and is written LF-forced (review MINOR 1 fix), making its sha256 platform- and time-independent.

This module does not itself convert raw Codex token usage into normalized credits -- the "25
credits = $1.00" rate is a separate, still-open pin (design doc:297-300, `HANDOFF.md:298`), now to
be pinned for the exact model `gpt-5.6-sol`; guessing a rate here risked a real run silently
under/over-tripping, so the breaker deliberately operates on already-normalized deltas and composes
with a converter once that rate is pinned.

**Launch-path wiring + KILL CONTRACT:** `tools/run_gate0_codex.ps1` is pinned free-handshake-only
(no `codex exec` path; must still end in `exit 1` -- `tests/test_run_gate0_codex_launcher.py::test_launcher_is_free_handshake_only_and_fail_closed`).
This PR does not add a live exec call to that script (would break that pinned invariant and would be
fabricating paid-execution capability outside this PR's scope). Instead `tools/run_gate0_codex.ps1`
carries a comment at its free-handshake exit point naming `tools/gate0_credit_breaker.py` as the
component the future paid launcher wraps its streaming `codex exec --json` output through. The
wired caller must feed `run_breaker(raise_on_trip=True, stall_timeout_s=STALL_TIMEOUT_S)` an
ITERATOR pulled lazily from the stream and kill the codex child the instant the breaker raises ANY
exception -- `BreakerTripped` OR `MalformedCreditStream` (review MINOR 2: catching only the former
is fail-open; a malformed or stalled stream crashes the accountant while the child keeps spending).

## The dry run

Command:
```
uv run --frozen python tools/gate0_credit_breaker.py dry-run-synthetic --out runs/gate0_live_breaker/live_breaker_dry_run_trip.json
```

Console output (2026-07-21 regeneration, deterministic artifact):
```
{"out": "runs\\gate0_live_breaker\\live_breaker_dry_run_trip.json", "status": "PASS", "trip": {"credits_at_trip": 252.0, "event_index_at_trip": 41, "events_in_stream": 45, "events_seen_before_halt": 42, "final_total_normalized_credits": 252.0, "halted_before_exhausting_stream": true, "limit_normalized_credits": 250, "source_kind": "sized_sequence", "tripped": true, "unconsumed_events_after_halt": 3}}
```

**Trip evidence:** the synthetic stream is 45 events of 6 normalized credits each (270 total if
fully consumed). The running total first reaches the 250 limit at event index 41 (0-based, the 42nd
event: `42 * 6 = 252 >= 250`). The breaker stopped there: `events_seen_before_halt = 42`,
`events_in_stream = 45`, `unconsumed_events_after_halt = 3` -- three events (`turn` 42, 43, 44) were
never read. The tail claim is honest by construction: the source is a sized sequence
(`source_kind: sized_sequence`), whose length is known without consuming it; for lazy sources the
receipt refuses to claim a tail at all (review MAJOR 1), and genuine non-consumption is separately
proven by the poisoned-generator and counting-source regression tests in
`tests/test_gate0_credit_breaker.py`.

`runs/gate0_live_breaker/live_breaker_dry_run_trip.json` SHA-256 (deterministic -- regenerable
byte-exactly on any platform; supersedes the 2026-07-19 timestamp-coupled hash `0fe2a4b1...`):
```
27538b256bfdf276af91d4533b83247361ddbe470c5682b8addd58bda340e734
```

## Artifact content

*(Reformatted for readability -- the `synthetic_credit_stream` array below is collapsed to two
objects per line, which the artifact's `json.dumps(..., indent=2)` rendering never emits, so this
block is NOT the byte rendering and does not hash to the pinned value; the pins review (MINOR 2)
correctly flagged the earlier "verbatim, byte-identical" claim here as false. The exact bytes
reproduce deterministically from the committed tool via the command above and hash to
`27538b256bfdf276af91d4533b83247361ddbe470c5682b8addd58bda340e734`.)*

```json
{
  "schema_version": 1,
  "kind": "live_credit_breaker",
  "status": "PASS",
  "limit_normalized_credits": 250,
  "mode": "dry_run_synthetic",
  "produced_by": "tools/gate0_credit_breaker.py:dry_run_synthetic",
  "synthetic_credit_stream": [
    {"turn": 0, "normalized_credits": 6}, {"turn": 1, "normalized_credits": 6},
    {"turn": 2, "normalized_credits": 6}, {"turn": 3, "normalized_credits": 6},
    {"turn": 4, "normalized_credits": 6}, {"turn": 5, "normalized_credits": 6},
    {"turn": 6, "normalized_credits": 6}, {"turn": 7, "normalized_credits": 6},
    {"turn": 8, "normalized_credits": 6}, {"turn": 9, "normalized_credits": 6},
    {"turn": 10, "normalized_credits": 6}, {"turn": 11, "normalized_credits": 6},
    {"turn": 12, "normalized_credits": 6}, {"turn": 13, "normalized_credits": 6},
    {"turn": 14, "normalized_credits": 6}, {"turn": 15, "normalized_credits": 6},
    {"turn": 16, "normalized_credits": 6}, {"turn": 17, "normalized_credits": 6},
    {"turn": 18, "normalized_credits": 6}, {"turn": 19, "normalized_credits": 6},
    {"turn": 20, "normalized_credits": 6}, {"turn": 21, "normalized_credits": 6},
    {"turn": 22, "normalized_credits": 6}, {"turn": 23, "normalized_credits": 6},
    {"turn": 24, "normalized_credits": 6}, {"turn": 25, "normalized_credits": 6},
    {"turn": 26, "normalized_credits": 6}, {"turn": 27, "normalized_credits": 6},
    {"turn": 28, "normalized_credits": 6}, {"turn": 29, "normalized_credits": 6},
    {"turn": 30, "normalized_credits": 6}, {"turn": 31, "normalized_credits": 6},
    {"turn": 32, "normalized_credits": 6}, {"turn": 33, "normalized_credits": 6},
    {"turn": 34, "normalized_credits": 6}, {"turn": 35, "normalized_credits": 6},
    {"turn": 36, "normalized_credits": 6}, {"turn": 37, "normalized_credits": 6},
    {"turn": 38, "normalized_credits": 6}, {"turn": 39, "normalized_credits": 6},
    {"turn": 40, "normalized_credits": 6}, {"turn": 41, "normalized_credits": 6},
    {"turn": 42, "normalized_credits": 6}, {"turn": 43, "normalized_credits": 6},
    {"turn": 44, "normalized_credits": 6}
  ],
  "synthetic_credit_stream_sha256": "75ecc19b38def371857b439a8692e0b568130a753d11183f480bea1eed0ecff7",
  "trip": {
    "tripped": true,
    "limit_normalized_credits": 250,
    "credits_at_trip": 252.0,
    "event_index_at_trip": 41,
    "events_seen_before_halt": 42,
    "events_in_stream": 45,
    "unconsumed_events_after_halt": 3,
    "halted_before_exhausting_stream": true,
    "source_kind": "sized_sequence",
    "final_total_normalized_credits": 252.0
  },
  "note": "Dry run with a synthetic credit stream (not a real Codex run): this artifact proves DETECTOR correctness only, per reports/2026-07-18-gate0-prereg.md precondition 4's tightening -- an actual demonstrated TRIP with a counted unconsumed tail (sized source), not a self-declared PASS. It does not prove halting of paid consumption (unread != unspent): precondition 4 status is COMPONENT MET -- WIRING PENDING, and the paid launch additionally requires the 4a-4d wired-path checklist banked on PR #118 (token->credit rate pinned for gpt-5.6-sol; iterator-fed run_breaker(raise_on_trip=True) killing the child on ANY breaker exception; a wired-path TRIP receipt against a zero-spend stub emitter with child-termination evidence; the pre-registered 300 s stall backstop)."
}
```

## Precondition-4 status: COMPONENT MET -- WIRING PENDING (not launch-satisfying alone)

Adopted verbatim from the PR #118 breaker review's ruling (its stricter reading of design
doc:243-246 governs, per the pre-reg's tighten-not-loosen law):

Proves: DETECTOR correctness -- the breaker halts **reading** at `>= 250` on an iterator source
with no post-hoc sum (this receipt's counted tail on a sized source; genuine non-consumption
proven by the poisoned-generator and counting-source regression tests).

Does not prove: halting of **paid consumption** (unread != unspent -- there is no process to kill
in a dry run); behavior against a real Codex token-usage stream (the token->credit conversion rate
is still unpinned -- design doc:297-300, now to be pinned for `gpt-5.6-sol`); or "exact wake
accounting" (a separate, larger, still-open C0 item per `reports/2026-07-14-gate0-readiness.md` --
out of this PR's scope).

Before any paid launch, ALL of (banked as the 4a-4d checklist in the PR #118 body):
**(4a)** token->normalized-credit conversion pinned for the exact model (`gpt-5.6-sol`), wired in
front of `run_breaker()`; **(4b)** the paid launcher wraps streaming `codex exec --json` through
`run_breaker(raise_on_trip=True)` passing an ITERATOR and kills the codex child on ANY breaker
exception (`BreakerTripped` or `MalformedCreditStream`); **(4c)** a wired-path TRIP receipt against
a zero-spend stub codex emitter -- evidence must include child-process termination (exit + lifetime)
plus the emitter's unsent tail, "events unread" alone is insufficient; **(4d)** the wall-clock
stall backstop armed (`stall_timeout_s=STALL_TIMEOUT_S`, pre-registered 300 s). The paid launch may
not proceed on the synthetic receipt alone.
