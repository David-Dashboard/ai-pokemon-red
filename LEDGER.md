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
- PR #111 received a posted `REQUEST CHANGES` review. Its four P0 findings were:
  fresh-project trust, self-declared receipts, mutable Docker tags, and no
  enforceable wake/credit breaker.
- The review fixes are in progress without a model call or held-out preflight:
  the launcher is now free-handshake-only, uses explicit CLI overrides and an
  immutable image ID, proves live MCP inventory plus host/image code parity,
  emits `paid_execution_enabled=false`, and has no model-execution path. The
  checker requires separately frozen expected pins, recomputes artifacts, and
  compares cross-arm common-brain receipts.

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
- [x] Implement the isolated free Codex handshake and fail-closed transcript/inventory checker.
- [x] Amend the Gate 0 design for Codex subscription accounting.
- [x] Run targeted component tests.
- [x] Run the final full tracked-project suite (`1141 passed`; security tests consolidated).
- [x] Open PR #111.
- [x] Obtain posted adversarial review.
- [x] Finish verification, push every review fix, and obtain posted re-review approval.

## Next
- David merges PR #111. Posted re-review approved `dbcfcda`; the final follow-up
  commit records status only and changes no executable/test behavior.
- After merge and image rebuild, resolve the executable path and run the free
  handshake. It cannot call a model and must remain `NO_GO_INSUFFICIENT_WAKES`.
- A paid launcher does not exist. Build/review one only after observable wake
  accounting and a live 250-credit breaker are mechanically proven.
- After David merges the readiness PR, run R0 + W0 + C0 only.
- A subscription-quota pre-registration/run is allowed only if all three return `GO`.
