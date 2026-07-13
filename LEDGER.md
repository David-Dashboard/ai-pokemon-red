# Ledger - entity v5 candidate shortlist (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Write `reports/2026-07-13-entity-v5-candidate-shortlist.md`: a $0 shortlist
across several candidate scenarios/games for the entity-gate v5 source-status
checks.

## Current status (2026-07-13)
- Branch: `codex/entity-v5-candidate-shortlist-2026-07-13`, cut from merged
  `main` at PR #108 (`914605e`).
- User asked to continue; token rotation is David-owned/trivial and not the
  blocker.
- Motivation: one-scenario probes are good for cheap kills, but v5 should not
  escalate until multiple candidate scenarios/games have been screened.

## Constraints
- No paid run. No v5 pre-registration.
- No scorer/code/tool-schema edits.
- Read-only artifact inspection and docs only unless explicitly added here.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Pull merged `main` after PR #108.
- [x] Branch-scan and create `codex/entity-v5-candidate-shortlist-2026-07-13`.
- [x] Claim shortlist task in HANDOFF/LEDGER.
- [x] Read existing v5/entity/world evidence.
- [x] Write `reports/2026-07-13-entity-v5-candidate-shortlist.md`.
- [ ] Verify, PR, and post adversarial-review comment.
