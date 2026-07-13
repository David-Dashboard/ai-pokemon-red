# Ledger - Gate 0 Codex subscription readiness

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Make the merged Minimum North Star Gate 0 launch-ready for one frozen Codex CLI
brain authenticated through David's ChatGPT subscription.

## Current status (2026-07-13)
- PR #110 merged to `main` as `cc81531`.
- David explicitly switched both future arms from Claude to Codex CLI.
- Branch: `codex/gate0-codex-readiness-2026-07-13`, from merged `main`.
- Branch scan found no overlapping remote readiness work.
- Codex is installed at the WindowsApps alias, but this task's sandbox cannot
  execute it even with escalation. The free auth/version handshake remains pending.

## Constraints
- No API key and no paid/subscription-quota brain run in this implementation task.
- No brain, `core/contracts.py`, or frozen MCP tool-schema change.
- Raw run/oracle artifacts remain append-only.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Confirm the Codex-provider plan and branch-scan.
- [x] Sync merged `main` and create the feature branch.
- [x] Claim the work in HANDOFF/LEDGER.
- [ ] Implement pinned MiniWoB seeds, seed/episode oracle logging, and one-attempt progression.
- [ ] Implement the sealed exact-seed reachability preflight.
- [ ] Implement the isolated ephemeral Codex launcher and NO_LEAK transcript/inventory checker.
- [ ] Amend the Gate 0 design for Codex subscription accounting.
- [ ] Run targeted/full tests, open PR, and obtain posted adversarial review.

## Next
- Commit/push this claim, then dispatch one Codex implementer with the agreed scope.
- After David merges the readiness PR, run R0 + W0 + C0 only.
- A subscription-quota pre-registration/run is allowed only if all three return `GO`.
