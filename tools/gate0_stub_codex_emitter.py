"""ZERO-SPEND stub codex emitter -- PR #118 checklist 4c proof fixture.

Makes NO network call, calls NO model, and never imports or invokes the real `codex` executable.
It exists solely to be substituted for `$ResolvedCodexPath` in `Invoke-BreakerSupervisedExec`
(tools/run_gate0_codex.ps1) so that function's REAL production plumbing -- relay, accountant,
breaker, kill contract -- can be proven end to end against a synthetic over-limit credit stream,
without ever running a paid `codex exec`.

Emits a deterministic JSONL stream on stdout shaped exactly like the real `token_count` events
this project observed from live (already-paid, pre-existing) Codex session rollouts on
2026-07-21 (see tools/gate0_codex_credit_rate.py's module docstring for that evidence): each line
is `{"type": "token_count", "info": {"total_token_usage": {...cumulative...}, "last_token_usage":
{...delta...}, "model_context_window": null}, "rate_limits": null}`. One pass-through
(non-token_count) event is interleaved to prove the accountant's zero-credit pass-through path
also runs on the real wired path, not just in unit tests.

Deliberately paced (`--delay-s` between events, default 0.2s) so a supervising process has a real
window to observe an in-flight stream and kill it mid-emission -- proving the kill is a genuine
interruption, not an artifact of racing a process that had already finished on its own.

`--out-progress` is written and flushed/fsynced after EVERY emitted line, independent of anything
the breaker/accountant observes -- this is the "emitter's unsent tail" evidence PR #118's
checklist 4c requires in addition to (not instead of) the breaker's own read-side halt evidence:
even a killed process leaves this file on disk recording exactly how far it got.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time


def main() -> int:
    # Windows Python, when stdout is redirected to a pipe (not a console), can pick a UTF-8
    # variant that prepends a byte-order mark to the very first write -- confirmed empirically
    # while first proving the wired path (a real `codex exec --json` stream, a Rust binary, would
    # not have this Python-specific quirk). Reconfigure explicitly to plain UTF-8, no BOM, no
    # newline translation, so the emitted JSONL is byte-clean for whatever reads it.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=int, default=45)
    parser.add_argument("--output-tokens-per-event", type=int, default=6)
    parser.add_argument("--delay-s", type=float, default=0.2)
    parser.add_argument("--out-progress", required=True)
    args = parser.parse_args()

    cumulative = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
                  "reasoning_output_tokens": 0, "total_tokens": 0}
    delta = {"input_tokens": 0, "cached_input_tokens": 0,
              "output_tokens": args.output_tokens_per_event, "reasoning_output_tokens": 0,
              "total_tokens": args.output_tokens_per_event}

    with open(args.out_progress, "w", encoding="utf-8", newline="\n") as progress:
        progress.write(json.dumps({"intended_total": args.total, "emitted_count": 0}) + "\n")
        progress.flush()
        os.fsync(progress.fileno())

        for i in range(args.total):
            if i == 3:
                # A real event with no known credit delta -- proves the pass-through path
                # (tools/gate0_codex_credit_rate.py::codex_event_to_credit_event) runs on the
                # actual wired stream, not only in isolated unit tests.
                sys.stdout.write(json.dumps({"type": "agent_message_delta", "delta": "..."}) + "\n")
                sys.stdout.flush()

            for field in cumulative:
                cumulative[field] += delta[field]
            event = {
                "type": "token_count",
                "info": {
                    "total_token_usage": dict(cumulative),
                    "last_token_usage": dict(delta),
                    "model_context_window": None,
                },
                "rate_limits": None,
            }
            sys.stdout.write(json.dumps(event) + "\n")
            sys.stdout.flush()

            with open(args.out_progress, "w", encoding="utf-8", newline="\n") as progress2:
                progress2.write(json.dumps({"intended_total": args.total, "emitted_count": i + 1}) + "\n")
                progress2.flush()
                os.fsync(progress2.fileno())

            time.sleep(args.delay_s)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
