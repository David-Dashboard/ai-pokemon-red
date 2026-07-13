# Ledger - Minimum North Star Gate 0 design (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Define the smallest honest cross-world integrated gate for the North Star, with
`$0` readiness work separated from future paid proof.

## Current status (2026-07-13)
- PR #109 merged to `main` as `1e1edd9`.
- David explicitly redirected the critical path from Cave Noire entity v5 to a
  Minimum North Star Gate.
- Branch: `codex/minimum-north-star-gate-0-2026-07-13`, cut from merged `main`.
- Gate 0 worlds: unbridged `pokemon_red` starter+rival task and new
  `miniwob_click_checkboxes` five-episode task.
- MKDS was removed from Gate 0 after the audit found broken perception plus a
  solution-bearing brief; it remains a later perception-readiness lane.
- PR #110 is open, CI green, and has a final posted adversarial APPROVE. Initial
  review's three blockers and re-review's paid-seed reachability blocker are
  closed; commit `8222ecf` seals the solution-free exact-seed preflight.
- Token rotation is David-owned/trivial and not the blocker.

## Constraints
- No paid run and no paid pre-registration under this task.
- No scorer/code/tool-schema edits.
- Documentation/read-only evidence only; raw outputs are append-only.
- Cave Noire source-status is paused, not run or deleted.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Pull merged `main` after PR #109.
- [x] Branch-scan and create `codex/minimum-north-star-gate-0-2026-07-13`.
- [x] Audit Red, MKDS, and MiniWoB run evidence and current tool surfaces.
- [x] Replace MKDS with MiniWoB click-checkboxes after David confirmation.
- [x] Write `reports/2026-07-13-minimum-north-star-gate-0-design.md`.
- [x] Append the superseding HANDOFF block and verify the complete diff.
- [x] Commit, push, open PR #110, and obtain the initial posted review.
- [x] Commit/push the review fixes and obtain posted re-review.

## Next
- David merges PR #110.
- After merge, plan the seed/client-isolation readiness build;
  then run R0 + W0 + C0 `$0` readiness only. A paid pre-registration is allowed
  only if all three return `GO`.
