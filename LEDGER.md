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
- David installed Codex with OpenAI's official PowerShell installer. This task
  still resolves the WindowsApps alias and receives access denied, so the free
  ChatGPT-auth/version/model handshake remains pending.
- Readiness implementation is complete on the feature branch without a model
  call or held-out preflight; the final tracked-project suite passed (`1163`).
  PR #111 is open; its posted adversarial-review gate remains open.

## Constraints
- No API key and no paid/subscription-quota brain run in this implementation task.
- No brain, `core/contracts.py`, or frozen MCP tool-schema change.
- Raw run/oracle artifacts remain append-only.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Confirm the Codex-provider plan and branch-scan.
- [x] Sync merged `main` and create the feature branch.
- [x] Claim the work in HANDOFF/LEDGER.
- [x] Implement pinned MiniWoB seeds, seed/episode oracle logging, and one-attempt progression.
- [x] Implement the sealed exact-seed reachability preflight.
- [x] Implement the isolated ephemeral Codex launcher and NO_LEAK transcript/inventory checker.
- [x] Amend the Gate 0 design for Codex subscription accounting.
- [x] Run targeted component tests.
- [x] Run the full tracked-project suite (`1163 passed`).
- [x] Open PR #111.
- [ ] Obtain posted adversarial review and address every finding.

## Next
- Obtain a posted adversarial review on PR #111 and address every finding before
  David merges.
- Resolve the executable path and complete the free auth/version/model handshake;
  keep C0 `NO_GO_INSUFFICIENT_WAKES` until wake accounting is grounded.
- After David merges the readiness PR, run R0 + W0 + C0 only.
- A subscription-quota pre-registration/run is allowed only if all three return `GO`.
