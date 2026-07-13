# Ledger - entity v5 bar redesign design doc (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Write and PR `reports/2026-07-13-entity-v5-bar-redesign.md`: a $0 design doc only, no code changes,
no scorer edits, no paid run. It must define a new v5 entity-grounding bar after v4 closed without a
paid attempt because the v3/v4 bar+world pair was honest-hostile.

## Current status (2026-07-13)
- Branch: `codex/entity-v5-bar-redesign-2026-07-13`, cut from current `main` after `git fetch` and
  branch scan. No overlapping `entity-v5` branch found.
- User authorized continuing without waiting; this task is the next non-paid item in `CODEX_HANDOFF.md`.
- Sources read: `HANDOFF.md`, `LEDGER.md`, `CODEX_HANDOFF.md`, `.claude/PROTOCOL.md`, `CLAUDE.md`,
  `reports/2026-07-11-entity-v4-verdict.md`, `reports/2026-07-05-northstar-capability-map.md`,
  `reports/2026-07-11-entity-v4-coverage-papercheck.md`,
  `reports/2026-07-11-entity-v4-visibility-probe.md`,
  `reports/2026-07-05-entity-v4-d-probe.md`.
- Local-only source wrinkle: `reports/2026-07-11-entity-v4-instrument-hunt.md` exists on disk but is
  untracked and absent from `origin/main`; decide during doc drafting whether the PR must include it as a
  receipt or avoid depending on it.

## Constraints
- No paid run. No rerun of banked entity v1-v4 verdicts. No scorer/code/tool-schema edits.
- New bar means new gate: no "stricter-only" carryover claims from v3/v4.
- Must address: replace forward-only `[n, n+15]`; forbid reactive same-step NEARs; cap NEAR cadence; pin
  press cadence; inherit #102 typed claims as-is; name North Star capability bought.

## Tasks
- [x] Read session/handoff/protocol sources and v4 verdict sources.
- [x] Fetch and scan remote branches; create dedicated feature branch from `main`.
- [x] Claim task in HANDOFF and re-arm LEDGER for v5 design.
- [x] Draft `reports/2026-07-13-entity-v5-bar-redesign.md`.
- [x] Run doc checks / review for coverage of required clauses: verifier found one MAJOR
  (decoy/rejection too soft), patch added plausible-comparator criteria, re-review PASS.
- [ ] Open PR and post at least one adversarial-review comment.
