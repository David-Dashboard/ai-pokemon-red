# ViZDoom yaw-flow fixtures (curated, committed)

28 frame pairs backing `tests/test_yaw_flow.py`'s regression floor for `core/yaw_flow.py` (P1
`YawBandFlow`, `reports/2026-07-04-vizdoom-3d-floor-design.md` S1.1). Sampled from the free offline
pre-check captures in `runs/vizdoom_precheck/` (gitignored, ~16 MB combined) — `basic_mixed/` and
`dtc_mixed/`, both captured WITH a per-step `actions.jsonl` action log, alignment convention
`frame_i = state BEFORE action_i` (so pair `(i, i+1)` reflects `action_i`).

**Not used:** the older 2026-07-02 `defend_the_center` probe capture — `PRECHECK_REPORT.md` (PC-2)
found it has an intermittent one-frame action<->frame misalignment (every 3rd cycle a `TURN_RIGHT`
lands one pair late). `dtc_mixed/` is the corrected re-capture with its own action log; only that one
is sampled here.

## Contents

- `pair{00..27}_a.png`, `pair{00..27}_b.png` — 320x240 RGB frame pairs (`frame_a` -> `frame_b`).
- `actions.json` — one record per pair: `action` (commanded action for that step), `source` (which
  precheck capture + episode it came from), and the R0 reading at fixture-selection time
  (`r0_dx_px`/`r0_direction`/`r0_confidence`, informational only — the test recomputes live).

## Composition (selected by `select_fixtures.py`, not hand-picked frame-by-frame)

- 10 `TURN_LEFT`, 12 `TURN_RIGHT` — sampled from pairs where the R0 estimator (at the pinned floors
  ncc>=0.2/prom>=0.02) already sign-agrees with the commanded turn, spread across both source
  captures and episodes.
- 6 `IDLE` — ego-stationary pairs (idle honesty check: must read `dx_px=0`/`direction="none"`, never
  false motion).
- Some of the 28 pairs are turn steps where R0 reports `None` at the pinned floors (high-rotation /
  low-texture pairs where the correlation peak is genuinely ambiguous) — kept deliberately so the
  committed set also exercises the `None` path, per PC-2's finding that in-burst fast turns produce a
  non-trivial None-rate even though sign is essentially never wrong.

## Provenance / regeneration

Not reproducible from a clean checkout alone (source captures are gitignored `runs/` output). To
regenerate from scratch: re-run `runs/vizdoom_precheck/capture_basic_mixed.py` and
`capture_dtc_mixed.py` (Docker + `vizdoom==1.3.0`, the PRECHECK_REPORT.md recipe), then re-run the
selection script used to build this directory (kept alongside PR-B's branch history, not committed
here — this is a curated snapshot, not a live pipeline).

## Numbers this fixture set achieves (measured on the committed 28 pairs, `core.yaw_flow` defaults)

See `tests/test_yaw_flow.py` for the exact assertions; committed-fixture sign-agreement and None-rate
are printed by that test and reported in the PR description. These are a regression floor (ARM (b)'s
bar from the design doc: sign-agreement >= 0.90, None-rate <= 0.50), not a re-derivation of PC-2's
own numbers (PC-2 used ~139 turn pairs across the full captures; this is a ~22-turn-pair subset).
