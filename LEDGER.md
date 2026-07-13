# Ledger - optional Kirby door/sub-room probe (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Run a `$0` local probe of the unverified Kirby door+enemy sub-room lead, then write
`reports/2026-07-13-kirby-door-probe.md` (short report, no code/scorer changes, no paid run).

## Current status (2026-07-13)
- Branch: `codex/kirby-door-probe-2026-07-13`, cut from current `main`.
- Source lead: `reports/2026-07-11-entity-v4-instrument-hunt.md`, currently local-only/untracked before
  this task; it found a door+enemy area from `kirby_to_death.state` but did not characterize it.
- v5 design requires any retained Kirby candidate to prove: visible pre-drop threat opportunities,
  plausible comparator/benign opportunities, 5+ drops / 30+ scoreable steps, cadence pinned, and no
  death spiral.
- Result: door is real and `move_blocked` works, but the lead is negative for v5 as-is: no hp=6
  near-door seed, no 5-drop/no-death supply, weak retreat, and no plausible benign comparator.
- PR: #108 open from `codex/kirby-door-probe-2026-07-13`; adversarial-review comment posted and CI green
  after reviewer fix commit `72a77bb`.

## Constraints
- No paid run. No v5 pre-registration. No scorer/code/tool-schema edits.
- Raw run/oracle artifacts are append-only; write fresh probe output only.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.
- Token rotation remains David-owned; do not print token values.

## Tasks
- [x] Pull merged `main` after PR #107.
- [x] Branch-scan and create `codex/kirby-door-probe-2026-07-13`.
- [x] Claim optional Kirby door/sub-room probe in HANDOFF/LEDGER.
- [x] Run local probe / gather measurements.
  - Evidence: fresh ignored output under `runs/kirby_door_probe_2026-07-13/`; `trace_*.jsonl`
    summaries plus `move_blocked/summary.json` from the official `run_skill` path.
- [x] Write `reports/2026-07-13-kirby-door-probe.md`.
- [x] Verify, PR, and post adversarial-review comment.
  - Evidence: `git diff --check`; local repo suite with local-only ignores passed 1129 tests, 2 warnings;
    GitHub CI passed on PR #108 after push.

## Next
- Await David merge/reject on PR #108.
- David-owned token rotation remains open.
- Do not rerun Kirby door checks unless David wants a manual hp=6 door-state capture.
