# Ledger - Gate 0 R0/W0/C0 readiness outcome

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Complete the coherent R0/W0/C0 `$0` readiness outcome: one two-arm offline scorer,
safe source-status probes where available, and one honest GO/NO_GO/INSUFFICIENT_SOURCE report.

## Current status (2026-07-14)
- Branch: `codex/gate0-r0-w0-c0-readiness-2026-07-14`, from merged PR #113.
- Complete R0 Red source status, W0 MiniWoB DEV source status, and C0 constancy/scoring readiness as one
  outcome-sized slice.
- Independently frozen expected pins, exact wake accounting, and the live 250-credit breaker are the
  known C0 critical-path source gaps.
- Readiness verdict is recorded on the current branch: R0/W0/C0 each `INSUFFICIENT_SOURCE`; paid Gate 0 `NO_GO`.
- Final current-head receipts are banked at `red-v3` and `miniwob-v2`; common brain, host/image parity,
  and tool inventories pass. Both remain `NO_GO_INSUFFICIENT_WAKES`, paid execution false.
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
- [x] Final canonical root-side `uv run --frozen`: targeted readiness `64 passed`; full tracked plus
  scorer `1159 passed, 1 warning`; diff check passed.
- [x] Rebuild final images and bank current-head `red-v3`/`miniwob-v2` free receipts.
- [ ] Independently freeze expected-pins JSON; do not claim full checker GO from observed receipts alone.
- [ ] Stage only intended files for parent commit/review.

## Next
- Finish tests and review this outcome slice. After merge, close only the banked readiness sources.
  Paid Gate 0 remains blocked until R0/W0/C0 all return `GO`.
