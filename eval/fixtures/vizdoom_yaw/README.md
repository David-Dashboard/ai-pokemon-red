# ViZDoom yaw-flow fixtures (curated, committed)

28 frame pairs (plus 6 known-limit pairs, below) backing `tests/test_yaw_flow.py` for
`core/yaw_flow.py` (P1 `YawBandFlow`, `reports/2026-07-04-vizdoom-3d-floor-design.md` S1.1). Sampled
from the free offline pre-check captures in `runs/vizdoom_precheck/` (gitignored, ~16 MB combined) —
`basic_mixed/` and `dtc_mixed/`, both captured WITH a per-step `actions.jsonl` action log, alignment
convention `frame_i = state BEFORE action_i` (so pair `(i, i+1)` reflects `action_i`).

**Not used:** the older 2026-07-02 `defend_the_center` probe capture — `PRECHECK_REPORT.md` (PC-2)
found it has an intermittent one-frame action<->frame misalignment (every 3rd cycle a `TURN_RIGHT`
lands one pair late). `dtc_mixed/` is the corrected re-capture with its own action log; only that one
is sampled here.

## Honest framing: what the main set is and is not

The main set is **curated by construction**: its turn pairs are sampled from pool pairs where R0
already sign-agrees at the pinned floors (see `select_fixtures.py`, committed here, deterministic
seed). Its numbers (sign-agreement 1.0 / None-rate 0.273) are therefore a **regression floor for the
implementation** — "the code still behaves as it did on these known-good, known-None, and known-idle
pairs" — NOT an unbiased measurement of pool performance. The pool-honest numbers are PC-2's
(`runs/vizdoom_precheck/PRECHECK_REPORT.md`): sign-agreement 0.964 / None-rate 0.201 over ~139 turn
pairs at the same floors.

The pool's failing pairs are **not discarded**: every one of them (6 total out of ~139 turn + 177
idle pool pairs) is committed under `known_limits/` and pinned by its own test, which asserts the
current failing behavior so the limits stay visible rather than hidden.

## Contents

- `pair{00..27}_a.png`, `pair{00..27}_b.png` — 320x240 RGB frame pairs (`frame_a` -> `frame_b`).
- `actions.json` — one record per pair: `action` (commanded action for that step), `source` (which
  precheck capture + episode it came from), and the R0 reading at fixture-selection time
  (`r0_dx_px`/`r0_direction`/`r0_confidence`, informational only — the test recomputes live).
- `select_fixtures.py` — the committed sampler that built both groups (deterministic, auditable).
- `known_limits/` — `limit{00..05}_{a,b}.png` + `actions.json`, same record shape.

## Main-set composition (selected by `select_fixtures.py`, not hand-picked frame-by-frame)

- 10 `TURN_LEFT`, 12 `TURN_RIGHT` — sampled from pairs where the R0 estimator (at the pinned floors
  ncc>=0.2/prom>=0.02) already sign-agrees with the commanded turn, spread across both source
  captures and episodes.
- 6 `IDLE` — ego-stationary pairs (idle honesty check: must read `dx_px=0`/`direction="none"`, never
  false motion).
- Some of the 28 pairs are turn steps where R0 reports `None` at the pinned floors (high-rotation /
  low-texture pairs where the correlation peak is genuinely ambiguous) — kept deliberately so the
  committed set also exercises the `None` path, per PC-2's finding that in-burst fast turns produce a
  non-trivial None-rate even though sign is essentially never wrong.

## known_limits/ composition (exhaustive, no sampling)

Every pool pair where R0 at the pinned floors fails, in either of the two observed modes:

- 4 wrong-sign turn pairs (all `basic_mixed`): a confidently-reported direction contradicting the
  commanded turn, all at near-floor confidence (<= 0.028 vs prom_floor 0.02). Three are the same
  burst-turn artifact (dx=-46 at confidence 0.0222) recurring once per episode.
- 2 false-motion idle pairs (both `dtc_mixed`): dx=+1 single-pixel jitter at moderate confidence —
  defend_the_center's monsters keep walking while the camera idles, nudging the band profile. Scene
  motion misread as ego motion.

`tests/test_yaw_flow.py::test_known_limits_document_the_r0_failure_modes` asserts these failures
still happen; if R0 ever stops failing on one, that test fails and the pair should be promoted to
the main set — the limits can shrink, never silently vanish.

## Provenance / regeneration

Not reproducible from a clean checkout alone (source captures are gitignored `runs/` output). To
regenerate from scratch: re-run `runs/vizdoom_precheck/capture_basic_mixed.py` and
`capture_dtc_mixed.py` (Docker + `vizdoom==1.3.0`, the PRECHECK_REPORT.md recipe), then from the repo
root: `python eval/fixtures/vizdoom_yaw/select_fixtures.py` (deterministic — reproduces both groups).
