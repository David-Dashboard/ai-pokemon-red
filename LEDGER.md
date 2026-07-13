# Ledger - Gate 0 Codex executable-resolution fix

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Resolve exactly one `.exe` Codex application into a scalar path before the free
Gate 0 handshake launcher uses or records it.

## Current status (2026-07-14)
- Branch: `codex/fix-gate0-codex-resolution-2026-07-14`.
- Merged main returned two Codex application candidates, `codex.exe` and the
  extensionless `codex`; `$codex.Source` therefore became multi-valued and the
  launcher attempted a malformed concatenated path.
- Both Docker images were already rebuilt and hash-matched. No auth, MCP, model,
  handshake, or preflight step ran.

## Constraints
- Touch only HANDOFF.md, LEDGER.md, tools/run_gate0_codex.ps1, and
  tests/test_run_gate0_codex_launcher.py.
- Do not run Codex/model/handshake/preflight, rebuild images, spend, push, or open a PR.
- Do not weaken any existing launcher guard or add model execution.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Claim the fix in HANDOFF and LEDGER.
- [x] Resolve all application candidates and require exactly one `.exe` source.
- [x] Use one scalar resolved path for version, login, MCP list, hashes, and receipt.
- [x] Add narrow regression coverage.
- [x] Run AST parsing and targeted/full tracked tests (`8 passed`; `1142 passed`).
- [x] Run final `git diff --check`.
- [x] Commit only the four scoped files.

## Next
- Parent reviews the scoped commit. Free handshake remains a separate action.
