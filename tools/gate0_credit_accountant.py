"""Gate 0 precondition 4b -- the live breaker accountant subprocess.

Spawned by `tools/run_gate0_codex.ps1`'s `Invoke-BreakerSupervisedExec` (PR #118 checklist 4b).
PowerShell relays the codex (or, for the zero-spend precondition-4c proof, the stub emitter's)
child process's stdout into THIS process's stdin as a live byte stream (.NET
`Stream.CopyToAsync`, never buffered on the PowerShell side). This process's exit is the kill
signal PowerShell acts on: the instant it exits for any reason other than the child already
having finished on its own, PowerShell tree-kills the child (`taskkill /T /F`).

Never buffers the input: `_credit_events()` is a plain generator over `sys.stdin`, so
`run_breaker`'s MAJOR-1 lazy-iterator guarantee (tools/gate0_credit_breaker.py) holds all the way
from the child's stdout to the trip decision -- nothing here ever calls `list()` on the stream.

Exit codes: 0 = stream ended cleanly without tripping (COMPLETED); 2 = a kill-worthy breaker
exception fired (TRIPPED or MALFORMED -- deliberately the SAME code, so a caller cannot
accidentally special-case away the fail-open MalformedCreditStream path); 3 = the credit-rate pin
itself was invalid (RATE_NOT_PINNED) -- refused before a single stream byte was read.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

from tools.gate0_codex_credit_rate import (
    CreditRateNotPinned,
    codex_event_to_credit_event,
    load_credit_rate_pin,
)
from tools.gate0_credit_breaker import BreakerTripped, MalformedCreditStream, STALL_TIMEOUT_S, run_breaker


def _credit_events(rate_pin: dict):
    """Lazily read raw JSONL lines from stdin, yielding normalized_credits events one at a time.

    Decodes as utf-8-sig rather than plain utf-8: a leading byte-order mark on the very first line
    is a benign encoding artifact of whatever wrote the stream (observed empirically from a
    Windows Python child's redirected stdout -- tools/gate0_stub_codex_emitter.py), never a real
    stream fault -- utf-8-sig strips a BOM if present and is byte-identical to utf-8 otherwise, so
    this never masks a genuinely malformed line."""
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8-sig")
    for index, line in enumerate(stdin):
        line = line.strip()
        if not line:
            continue
        try:
            raw_event = json.loads(line)
        except Exception as exc:
            raise MalformedCreditStream(f"malformed_json_line:{index}") from exc
        try:
            yield codex_event_to_credit_event(raw_event, rate_pin)
        except ValueError as exc:
            raise MalformedCreditStream(f"malformed_token_usage:{index}:{exc}") from exc


def _write_verdict(path: Path, verdict: dict) -> None:
    # newline="\n" keeps this readable cross-platform; PowerShell reads it back via ConvertFrom-Json,
    # which does not care about line endings, but consistency with the rest of this tool family
    # (gate0_credit_breaker.py) avoids a stray CRLF trap.
    path.write_text(json.dumps(verdict) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate-pin", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--verdict-out", type=Path, required=True)
    parser.add_argument("--stall-timeout-s", type=float, default=float(STALL_TIMEOUT_S))
    # PR #122 coordinator M4: the combined <=250 ceiling across both arms (reports/2026-07-18-
    # gate0-prereg.md) is enforced by seeding this run's breaker with whatever an earlier arm
    # already consumed -- tools/run_gate0_codex.ps1 reads that from the cross-arm ledger and
    # passes it here. 0.0 (default) preserves single-invocation behavior exactly.
    parser.add_argument("--starting-credits", type=float, default=0.0)
    args = parser.parse_args()

    try:
        rate_pin = load_credit_rate_pin(args.rate_pin, args.model)
    except CreditRateNotPinned as exc:
        _write_verdict(args.verdict_out, {"result": "RATE_NOT_PINNED", "error": str(exc)})
        return 3

    try:
        trip = run_breaker(_credit_events(rate_pin), raise_on_trip=True,
                            stall_timeout_s=args.stall_timeout_s, starting_credits=args.starting_credits)
    except BreakerTripped as exc:
        _write_verdict(args.verdict_out, {
            "result": "TRIPPED",
            "credits_at_trip": exc.credits_at_trip,
            "event_index_at_trip": exc.event_index,
            "events_seen": exc.events_seen,
        })
        return 2
    except MalformedCreditStream as exc:
        _write_verdict(args.verdict_out, {"result": "MALFORMED", "error": str(exc)})
        return 2

    _write_verdict(args.verdict_out, {"result": "COMPLETED", "trip": trip})
    return 0


if __name__ == "__main__":
    exit_code = main()
    # os._exit(), not SystemExit/sys.exit(): found empirically while proving PR #122's M2 fix.
    # tools/gate0_credit_breaker.py::_timed_iter's stall backstop runs a daemon thread that may
    # still be blocked mid-read on this process's stdin (real bytes are still arriving from a
    # still-running child even after THIS process has already tripped and is exiting). A normal
    # interpreter shutdown races that thread against stdin's buffered-I/O lock and can crash with
    # "_enter_buffered_busy: could not acquire lock ... at interpreter shutdown" (observed:
    # STATUS_ACCESS_VIOLATION), which delayed PowerShell's supervisor from noticing this process
    # had exited by several seconds -- directly undermining the "kill immediately" contract this
    # process exists to serve. The verdict file is already fully written and closed by
    # _write_verdict() above (a synchronous, already-closed file write) before this line runs, so
    # skipping normal finalization here loses nothing: os._exit() terminates immediately via the
    # OS syscall, without waiting on or racing any daemon thread.
    os._exit(exit_code)
