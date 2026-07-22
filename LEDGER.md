# Ledger - Gate 0 R0/W0/C0 readiness outcome

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative -> HANDOFF.md. -->

## Goal
Complete the coherent R0/W0/C0 `$0` readiness outcome: one two-arm offline scorer,
safe source-status probes where available, and one honest GO/NO_GO/INSUFFICIENT_SOURCE report.

**2026-07-21 (this slice):** produce the FINAL Gate 0 readiness stamp + David's signature package
against current `main` (`61abba7`, PR #125 merged) — supersedes the stale `docs/gate0-stamping`
(PR #124). Re-verify the 9 preconditions, prove the gate can now `PASS` (synthetic manifest through
`score()`), compute every signature-time hash answerable ahead of signature, and hand David the
exact fields he still needs to supply.

## Current status (2026-07-21)
- Branch: `docs/gate0-readiness-final-v2`, from merged `main`@`61abba7` (PR #125). Supersedes the
  stale `docs/gate0-stamping` (PR #124), which predated PR #125's Cheap-basis amendment.
- **GATE 0 IS LAUNCH-READY, PENDING DAVID'S SIGNATURE + QUOTA CHECK.** 9-precondition table
  re-verified against current `main`: 1–7, 9 `MET`; 8 (Codex-pool quota) `LAUNCH-TIME` by design
  (checked immediately before each arm's launch). Full detail, computed hashes, and the signature
  package: `reports/2026-07-21-gate0-readiness-final-v2.md`.
- Proven this session: a synthetic manifest through `eval/score_gate0.py::score()` (clean audits,
  real banked human baselines 233.288s/271 red, 224.83s/18 miniwob, in-cap metrics) returns
  `overall=PASS`/`readiness=GO` — the gate's PASS path is mechanically reachable now. An over-cost
  variant correctly returns `FAIL_CHEAP`.
- `tools/check_gate0_codex.py` re-run against the fresh `red-v4`/`miniwob-v3` free-handshake
  receipts (2026-07-21, pinned model `gpt-5.6-sol`, rebuilt images) with current merged pins:
  `constancy_failures` reduces to exactly the two by-design `CONSTRAINT:launch-invocation-dependent-
  recompute-at-signature` fields (`config_sha256`, `codex_mcp_list_sha256`); all other 18
  `PIN_FIELDS` match; `peer_constancy: PASS` both arms.
- Human baselines (precondition 6) are now captured (David, 2026-07-21): red via Option-A
  reconstruction (`reports/2026-07-21-gate0-red-baseline-reconstruction.md`), miniwob via 5 fresh
  DEV episodes. **Gap closed same-day:** the source-pins fixtures' `red_human`/`miniwob_human`
  `artifact_sha256` pins are now frozen to the real, independently recomputed hashes of the
  captured files (`5144a5b3...`/`32b0c021...`); `paid_gate0`'s `miniwob_human` correctly stays
  `PENDING` (a genuinely different, not-yet-built paid-seed replay artifact). Proven via the real
  loader (`eval.score_gate0._verify_sources`): no `red_human`/`miniwob_human` failure in either
  mode (except the correctly-still-pending `paid_gate0` miniwob one); the synthetic-PASS proof
  still holds unchanged.
- Live breaker (precondition 4) is fully wired and merged (PR #122): `Confirm-PaidExecSignature`,
  `Invoke-BreakerSupervisedExec`, combined cross-arm ledger; wired-path zero-spend TRIP receipt
  `status=PASS`, `credits_at_trip=252.0`.
- Wake accounting stays DEFERRED, non-gating (David's 2026-07-21 decision, PR #125/#126) — Cheap
  rests on cost-per-task only, unchanged caps.
- Current North Star score is unchanged (overall 19/100, engineering 76/100, proof 8/100) — this
  slice is readiness/interpretability only, no paid run.

## Constraints
- Never run `codex exec` or any model/paid path.
- Do not expose paid-held-out MiniWoB seeds `1000..1004`.
- No brain, `core/contracts.py`, agent-visible tool schema, or frozen handshake artifact edits.
- Raw probe artifacts are append-only and every run uses a unique output directory.
- Do not touch unrelated untracked Spanish-teacher files or local agent/config dirs.

## Tasks
- [x] Claim the complete readiness slice in HANDOFF and LEDGER before production edits.
- [x] Add Red offline battle + first-party HP watch signals from existing memory-map constants, and
  fail closed when HP reaches zero before trainer-battle exit.
- [x] Implement one fail-closed two-arm offline Gate 0 scorer.
- [x] Add synthetic PASS/failure/insufficient-source coverage.
- [x] Check safe deterministic R0/W0 DEV probe paths; bank exact source blockers without running
  destructive fixed-output scripts or held-out seeds.
- [x] Write the readiness report and update scorecard/continuity.
- [x] Final post-review-fix canonical root-side `uv run --frozen`: targeted readiness
  `71 passed in 1.02s`; full tracked plus scorer `1166 passed, 1 warning in 23.74s`; `py_compile` and diff
  check passed.
- [x] Rebuild final images and bank current-head `red-v3`/`miniwob-v2` free receipts.
- [x] Independently freeze expected-pins JSON (PR #118) — `eval/fixtures/gate0_expected_pins_{red,miniwob}.json`.
- [x] Close PR #114 self-declared-GO finding: fixed modes/seeds, fixed expected-pins paths, hash-verified
  metric/wake/breaker artifacts, strict-positive human/agent measurements, and bare-claim rejection.
- [x] Close PR #114 Red finding: exact first `0 -> 1`; battle after acquisition; HP/map safety through
  all ten sustained-exit rows; delayed-zero and delayed-map regressions.
- [x] Close PR #114 MiniWoB finding: exact episode/seed set, exactly one successful terminal each, and
  rejection of extras, conflicts, duplicates, or abandoned-then-success histories.
- [x] Canonical root-side post-review verification complete; ready for re-review.

### 2026-07-21 final-stamp-v2 slice
- [x] Re-verify both human baselines exist, load, recompute sha256 (§2 of the report).
- [x] Re-run `tools/check_gate0_codex.py` against the fresh `red-v4`/`miniwob-v3` receipts with
  current merged pins/scorer; quote verbatim output both arms.
- [x] Construct the minimal synthetic successful manifest and prove `score()` reaches `PASS`/`GO`;
  prove an over-cost variant reaches `FAIL_CHEAP`.
- [x] Re-verify the 9-precondition table against current `main`.
- [x] Compute the 2 signature-time hashes' recipe (worked example) + the 4 safety-critical
  canonical git-blob hashes at `61abba7`.
- [x] Write `reports/2026-07-21-gate0-readiness-final-v2.md` with the full signature package.
- [x] Update LEDGER.md + HANDOFF.md top block.
- [x] Full suite green (`1386 passed, 16 skipped in 54.24s`).
- [x] Freeze `red_human`/`miniwob_human` `artifact_sha256` pins in
  `eval/fixtures/gate0_{readiness_dev,paid}_source_pins.json` against the real captured baseline
  files; prove via the real loader (no PENDING, no mismatch); re-confirm synthetic-PASS still
  holds; full suite green after the freeze (`1386 passed, 16 skipped in 51.47s`).
- [ ] Stage only intended files for parent commit/review.

## Next
- PR + adversarial review for this readiness-stamp-v2 slice. After merge: David signs
  `eval/fixtures/gate0_signature.json` per the report's Signature Package, confirms quota
  (precondition 8), and launches Arm R then Arm W. Paid Gate 0 remains blocked until David signs
  and quota is confirmed.
