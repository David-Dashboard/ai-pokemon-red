# Ledger - Gate 0 two-arm free-handshake compatibility

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Make both free handshake-only Gate 0 arms emit safe receipts with intentional
`NO_GO_INSUFFICIENT_WAKES`, without any model execution or spend.

## Current status (2026-07-14)
- Branch: `codex/gate0-free-handshake-compat-2026-07-14`, from merged PR #112.
- PR #113 is open. Review found production code and append-only receipt artifacts clean; its blockers
  were docs-only score/spend derivation and stale current status, now addressed locally.
- Both free handshakes are complete with validated safe receipts from the exact user-local Codex CLI
  0.144.3 path, ChatGPT authentication, immutable image/code parity, and exact per-arm tool inventories.
- Readiness remains intentionally `NO_GO_INSUFFICIENT_WAKES`; no model or held-out preflight ran.
- Current experiment blockers are R0/W0/C0, exact wake accounting, a live 250-credit breaker, and a
  frozen reviewed paid pre-registration.

## Constraints
- This review fix touches only HANDOFF.md, LEDGER.md, and NORTH_STAR_SCORECARD.md.
- Run only the explicitly approved free handshake commands; never `codex exec`.
- No model call, held-out preflight/content, API key, spend, brain/scorer/schema change, or image rebuild.
- Handshake artifacts are append-only; every compatibility retry uses a unique output directory.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Claim the gate-sized two-arm compatibility slice.
- [x] Implement stderr-safe production login-status capture with exact scalar executable and fixed args.
- [x] Behaviorally test the exact production helper AST for stderr success and nonzero exit.
- [x] Run AST parsing and targeted launcher tests (`15 passed`).
- [x] Run the Red free handshake to safe receipt output.
- [x] Run the MiniWoB free handshake to safe receipt output.
- [x] Verify both receipts and record every append-only attempt/blocker.
- [x] Add the blunt tracked North Star scorecard.
- [x] Run the full tracked suite (`1149 passed`) and `git diff --check`.
- [x] Stage only the intended tracked files for parent commit.
- [x] Replace unsupported score deltas with the first explicit engineering/proof rubric and formula.
- [x] Add deduplicated exact and estimated historical usage manifests with tracked source locators.
- [x] Correct PR #113 review/current-next status without touching production or receipts.
- [x] Verify score/spend arithmetic and `git diff --check`.
- [x] Stage only the three docs for parent commit.

## Attempts
- Red attempt 1: `runs/gate0_codex_handshake_2026-07-14/red/` stopped before auth/MCP receipt. Windows
  PowerShell stripped embedded `"rb"` from the immutable-image Python hash program, which exited 1 with
  `NameError: rb`. No model or emulator started; the append-only path will not be reused.
- Red attempt 2: `runs/gate0_codex_handshake_2026-07-14/red-compat1/` passed login and immutable
  image/code parity, then failed because PowerShell stripped quotes from explicit TOML array overrides.
  Codex saw `[run,-i]` as a string instead of a sequence. No model or emulator started; the path will
  not be reused.
- Diagnostic: `runs/gate0_codex_handshake_2026-07-14/diagnostic-mcp-config1/` used only free
  `codex mcp list --json` calls to isolate TOML array quote loss; no model or world started.
- Red attempt 3: `runs/gate0_codex_handshake_2026-07-14/red-compat2/` emitted a validated safe receipt,
  SHA-256 `a76ef3be11890b5b257249ce3000b04e6768ac17fce68590ac2fa3de99849630`.
- MiniWoB attempt 1: `runs/gate0_codex_handshake_2026-07-14/miniwob/` emitted a validated safe receipt,
  SHA-256 `c4909f9d321f83e8ef0001b5f95e7f09de250cd276dcfd468fd685057b3e7a98`.

## Next
- Obtain posted approval on PR #113's current head and green CI, then David merges. After merge, complete
  R0/W0/C0 only. Paid Gate 0 remains `NO_GO` until wake accounting and a live breaker are proven.
