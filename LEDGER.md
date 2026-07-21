# Ledger - Gate 0 R0/W0/C0 readiness outcome

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Complete the coherent R0/W0/C0 `$0` readiness outcome: one two-arm offline scorer,
safe source-status probes where available, and one honest GO/NO_GO/INSUFFICIENT_SOURCE report.

## Current status (2026-07-14)
- Branch: `codex/gate0-r0-w0-c0-readiness-2026-07-14`, from merged PR #113.
- Complete R0 Red source status, W0 MiniWoB DEV source status, and C0 constancy/scoring readiness as one
  outcome-sized slice.
- Independently frozen expected pins and a proven live-breaker dry-run TRIP receipt are the known
  C0 critical-path source gaps (signature/launch-time items).
- **2026-07-21 update:** exact wake accounting is no longer a tracked blocker here. David decided
  Gate 0's Cheap axis is grounded on cost-per-task; wakes-per-task is DEFERRED (no per-model-decision
  observable exists in Codex's JSONL stream, `reports/2026-07-21-gate0-wake-grounding.md`) and
  `eval/score_gate0.py` no longer gates the verdict on it (`feat/gate0-wake-accounting`, PR #125).
- Readiness verdict is recorded on the current branch: R0/W0/C0 each `INSUFFICIENT_SOURCE`; paid Gate 0 `NO_GO`.
- Final current-head receipts are banked at `red-v3` and `miniwob-v2`; common brain, host/image parity,
  and tool inventories pass. Both remain `NO_GO_INSUFFICIENT_WAKES` at the readiness-receipt level
  (audit()'s fail-closed hardcode, per design — no paid execution has run), paid execution false.
- Preserve `runs/gate0_readiness_2026-07-14/miniwob-v1/` as an infra failure: a top-level Red memory-map
  import was unavailable in the intentionally lean MiniWoB image. The fix keeps Red addresses local to
  its registry entry; `miniwob-v1` is never reused. `red-v1` had no directory/receipt; `red-v2` is valid
  pre-final-code evidence superseded for parity.
- Current North Star score is overall 19/100, engineering 76/100, proof 8/100.

## Constraints
- Never run `codex exec` or any model/paid path.
- Do not expose paid-held-out MiniWoB seeds `1000..1004`.
- No brain, `core/contracts.py`, agent-visible tool schema, or frozen handshake artifact edits.
- Raw probe artifacts are append-only and every run uses a unique output directory.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Claim the complete readiness slice in HANDOFF and LEDGER before production edits.
- [x] Add Red offline battle + first-party HP watch signals from existing memory-map constants, and
  fail closed when HP reaches zero before trainer-battle exit.
- [x] Implement one fail-closed two-arm offline Gate 0 scorer.
- [x] Add synthetic PASS/failure/insufficient-source coverage.
- [x] Check safe deterministic R0/W0 DEV probe paths; bank exact source blockers without running
  destructive fixed-output scripts or held-out seeds.
- [x] Write the readiness report and update scorecard/continuity.
- [x] Final post-review-fix canonical root-side `uv run --frozen`: targeted readiness
  `71 passed in 1.02s`; full tracked plus scorer `1166 passed, 1 warning in 23.74s`; `py_compile` and diff
  check passed.
- [x] Rebuild final images and bank current-head `red-v3`/`miniwob-v2` free receipts.
- [ ] Independently freeze expected-pins JSON; do not claim full checker GO from observed receipts alone.
- [x] Close PR #114 self-declared-GO finding: fixed modes/seeds, fixed expected-pins paths, hash-verified
  metric/wake/breaker artifacts, strict-positive human/agent measurements, and bare-claim rejection.
- [x] Close PR #114 Red finding: exact first `0 -> 1`; battle after acquisition; HP/map safety through
  all ten sustained-exit rows; delayed-zero and delayed-map regressions.
- [x] Close PR #114 MiniWoB finding: exact episode/seed set, exactly one successful terminal each, and
  rejection of extras, conflicts, duplicates, or abandoned-then-success histories.
- [x] Canonical root-side post-review verification complete; ready for re-review.
- [ ] Stage only intended files for parent commit/review.

## Next
- Finish tests and review this outcome slice. After merge, close only the banked readiness sources.
  Paid Gate 0 remains blocked until R0/W0/C0 all return `GO`.
