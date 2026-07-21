# Ledger - Gate 0 final readiness stamping

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Stamp Gate 0's final readiness: record both human baselines + all preconditions into one honest
verdict, re-verify against `main`, and produce David's signature package.
`reports/2026-07-21-gate0-readiness-final.md`.

## Current status (2026-07-21)
- Branch: `docs/gate0-stamping`, own worktree from `origin/main`@`99c9fa7` (#122 merged).
- 8/9 pre-reg preconditions (`reports/2026-07-18-gate0-prereg.md`) are `MET`; #8 (quota check) is
  inherently launch-time.
- **New finding, not previously flagged as launch-blocking**: `tools/check_gate0_codex.py::audit()`
  hardcodes `wakes=None`/`wake_accounting="INSUFFICIENT_WAKES"` unconditionally (pinned by
  `tests/test_check_gate0_codex.py::test_exact_observed_pins_are_still_no_go_until_wakes_exist`).
  No `agent_metrics.json`/`wake_boundary.json` writer tool exists. Traced through
  `eval/score_gate0.py`: a genuinely successful paid run today would still score
  `INSUFFICIENT_DATA`/`INSUFFICIENT_SOURCE`, never `PASS`. Ruled explicitly in the report: this is
  a closable-at-$0 mechanism gap, not an inherent "only observable during the paid run" limit.
- Both human baselines verified present, loading, and hash-matched: Red (David, reconstructed,
  `wall_clock_s=233.288`, `primitive_actions=271`, sha256 `5144a5b3...`), MiniWoB (David, played,
  `wall_clock_s=224.83`, `primitive_actions=18`, 5/5 reward, sha256 `32b0c021...`).
- Computed fresh: the 4 PR #122 safety-critical file hashes (`expected_launcher_sha256` etc.,
  §3a of the report) and re-confirmed world-image parity/codex version/ROM+state hashes all match
  the frozen pins, at commit `99c9fa7`.
- `config_sha256`/`codex_mcp_list_sha256` remain genuinely launch-invocation-dependent
  (by design, per the expected-pins files) — could not be freshly demonstrated this session
  because the harness's auto-mode classifier refused to run `tools/run_gate0_codex.ps1` (spawns
  `docker`/`codex.exe`); not routed around per safety-invariants law 9. Does not newly block
  anything — see report §3b.
- Full suite green: `1369 passed, 16 skipped` (`uv run --frozen pytest -q`,
  `UV_PROJECT_ENVIRONMENT=.venv-win-stamp`).

## Constraints
- Never run `codex exec` or any paid path (not attempted; not needed for this task).
- Never touch the primary checkouts except read-only (human baseline artifacts, ROM/savestate
  copied read-only into this own worktree to exercise the free-handshake recipe).
- Machinery-frozen: this pass diagnoses and rules on the wake-accounting gap; it does not build the
  fix (out of scope for a stamping pass; flagged as a follow-up).
- Raw run artifacts under `runs/` are gitignored and append-only; nothing there was rewritten.

## Tasks
- [x] Own worktree from `origin/main` (verified #122 merged, `99c9fa7`).
- [x] Read the 2026-07-18 pre-reg's 9-precondition table + the 2026-07-14 readiness report +
      `tools/check_gate0_codex.py` + the #122 signature mechanism.
- [x] Verify both human baseline artifacts exist, load, and hash-match.
- [x] Re-run readiness end to end for everything not requiring the blocked launcher subprocess;
      compute where each precondition now stands.
- [x] Compute the 4 safety-file canonical hashes deterministically; document the
      launch-invocation-dependent status of the other 2 signature-time hashes.
- [x] Write `reports/2026-07-21-gate0-readiness-final.md`.
- [x] Update HANDOFF.md top block.
- [x] Full suite green.
- [ ] Commit, push, open PR.

## Next
Open the PR. David: read the report's §4 ruling before signing — decide whether to close the
wake-accounting gap first or explicitly accept the INSUFFICIENT_DATA risk.
