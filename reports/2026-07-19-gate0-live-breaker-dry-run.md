# Gate 0 live credit breaker -- dry-run TRIP receipt (precondition 4) -- 2026-07-19

`runs/` is gitignored (`.gitignore:27`), so the artifact this report documents lives only on the
producing machine at `runs/gate0_live_breaker/live_breaker_dry_run_trip.json` -- this report is the
committed evidence, per the pre-reg's own convention for `runs/` artifacts (e.g.
`reports/2026-07-14-gate0-readiness.md` citing `runs/gate0_readiness_2026-07-14/...` by hash rather
than committing it).

## What this closes

`reports/2026-07-18-gate0-prereg.md` precondition 4: "Live breaker dry-run TRIP receipt." The design
doc requires "a live breaker that halts at 250 normalized credits without relying on end-of-run
arithmetic" (`reports/2026-07-13-minimum-north-star-gate-0-design.md:244-246`); the pre-reg's
tightening over the scorer's mechanical check (`eval/score_gate0.py`'s `live_breaker` requirement,
`kind=live_credit_breaker`, `status=PASS`, `limit=250`) is that the artifact "must record an actual
dry-run TRIP ... not merely a self-declared PASS status" (`reports/2026-07-18-gate0-prereg.md` row 4).

## What was built

`tools/gate0_credit_breaker.py`:
- `run_breaker(events, limit=250)` -- consumes a stream of `{"normalized_credits": N}` events and
  stops accumulating THE INSTANT the running total is `>= limit`. It never processes events past the
  one that crosses the limit -- that is the actual halting property the design doc asks for, not a
  `sum()` computed after reading everything.
- `validate_event()` / `load_jsonl()` -- fail closed on a malformed stream (missing key, non-numeric,
  bool-as-numeric, NaN/inf, negative): raise `MalformedCreditStream` immediately rather than treating
  a bad event as zero and continuing.
- `dry_run_synthetic()` -- builds a deterministic synthetic 45-event stream (6 normalized credits
  each, 270 total), runs it through `run_breaker()`, and only ever writes `status: "PASS"` into the
  artifact if the run *actually* tripped *and* halted before exhausting the stream -- both computed
  from the real `run_breaker()` return value, never hand-typed.

This module does not itself convert raw Codex token usage into normalized credits -- the "25
credits = $1.00" rate is a separate, still-open pin (design doc:297-300, `HANDOFF.md:298`); guessing
a rate here risked a real run silently under/over-tripping, so the breaker deliberately operates on
already-normalized deltas and composes with a converter once that rate is pinned.

**Launch-path wiring:** `tools/run_gate0_codex.ps1` is pinned free-handshake-only (no `codex exec`
path; must still end in `exit 1` -- `tests/test_run_gate0_codex_launcher.py::test_launcher_is_free_handshake_only_and_fail_closed`).
This PR does not add a live exec call to that script (would break that pinned invariant and would be
fabricating paid-execution capability outside this PR's scope). Instead `tools/run_gate0_codex.ps1`
now carries a comment at its free-handshake exit point naming `tools/gate0_credit_breaker.py` as the
component the future paid launcher wraps its streaming `codex exec --json` output through (kill the
child the instant `run_breaker()` raises `BreakerTripped`). The breaker is therefore built and proven
correct now, against a synthetic stream, so wiring it in later is an import, not a new correctness
question.

## The dry run

Command:
```
uv run --frozen python tools/gate0_credit_breaker.py dry-run-synthetic --out runs/gate0_live_breaker/live_breaker_dry_run_trip.json
```

Console output:
```
{"out": "runs\\gate0_live_breaker\\live_breaker_dry_run_trip.json", "status": "PASS", "trip": {"credits_at_trip": 252.0, "event_index_at_trip": 41, "events_in_stream": 45, "events_seen_before_halt": 42, "final_total_normalized_credits": 252.0, "halted_before_exhausting_stream": true, "limit_normalized_credits": 250, "tripped": true, "unconsumed_events_after_halt": 3}}
```

**Trip evidence:** the synthetic stream is 45 events of 6 normalized credits each (270 total if
fully consumed). The running total first reaches the 250 limit at event index 41 (0-based, the 42nd
event: `42 * 6 = 252 >= 250`). The breaker stopped there: `events_seen_before_halt = 42`,
`events_in_stream = 45`, `unconsumed_events_after_halt = 3` -- three events (`turn` 42, 43, 44) were
never read. That is the demonstrated TRIP: the breaker halted AT the limit and left evidence (the
unconsumed tail) that it did not simply sum the whole stream after the fact.

`runs/gate0_live_breaker/live_breaker_dry_run_trip.json` SHA-256:
```
0fe2a4b119774941b15f28d3c7355f917a1f6b362a5bc044443570aa88698ed7
```

## Artifact content (verbatim, byte-identical to the local `runs/` copy)

```json
{
  "schema_version": 1,
  "kind": "live_credit_breaker",
  "status": "PASS",
  "limit_normalized_credits": 250,
  "mode": "dry_run_synthetic",
  "produced_by": "tools/gate0_credit_breaker.py:dry_run_synthetic",
  "produced_at_utc": "2026-07-18T22:17:59.479085+00:00",
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
    "final_total_normalized_credits": 252.0
  },
  "note": "Dry run with a synthetic credit stream (not a real Codex run): the breaker's own halting correctness is what this artifact proves, per reports/2026-07-18-gate0-prereg.md precondition 4's tightening -- an actual demonstrated TRIP with unconsumed events left behind, not a self-declared PASS. Wire run_breaker() around the real per-event Codex token-usage stream once the paid launcher exists; the token->normalized-credit conversion rate remains a separate open item (design doc:297-300)."
}
```

## What this does and does not prove

Proves: the breaker mechanism itself halts exactly at the 250-credit limit rather than computing a
post-hoc sum, on a synthetic stream, reproducibly (unit-tested in `tests/test_gate0_credit_breaker.py`).

Does not prove: behavior against a real Codex token-usage stream (the token->credit conversion rate
is still unpinned -- design doc:297-300), or "exact wake accounting" (a separate, larger, still-open
C0 item per `reports/2026-07-14-gate0-readiness.md`'s "no independently frozen expected pins, exact
wake accounting, or mechanical live 250-credit breaker" -- this report closes only the third of those
three; wake accounting is out of this PR's scope).
