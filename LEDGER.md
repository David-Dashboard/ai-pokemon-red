# Ledger - post-merge hygiene (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Refresh current truth after PR #105 and PR #106 merged. No code changes, no paid run, no scorer edits.

## Current status (2026-07-13)
- `main` includes PR #105 (`b027fcb`): MKDS continuous-time A/B verdict banked.
  - Primary batching bar: FAIL (`1.030x` observed vs `1.300x` required).
  - Conditional guard: PASS.
  - Spend: `$1.5488415` default-account spend; `$0` account-B blocked launch.
- `main` includes PR #106 (`75bb785`): entity v5 bar redesign doc banked.
  - Design only; no code/scorer/tool-schema changes.
  - No paid v5 run authorized or scheduled.
- Current branch for this hygiene PR: `codex/post-merge-hygiene-2026-07-13`.

## Open items
- David-owned: rotate the leaked `settings.local.json` bearer token from 2026-07-04. Do not print the
  token value.
- Optional: Kirby door/sub-room `$0` probe only if v5 retains Kirby and the lead is worth characterizing
  before a future v5 pre-registration.

## Tasks
- [x] Merge PR #106 after David explicitly delegated it.
- [x] Pull merged `main`.
- [x] Refresh `HANDOFF.md` and `LEDGER.md` to current post-merge truth.
- [ ] Open small hygiene PR and post/record review status.
