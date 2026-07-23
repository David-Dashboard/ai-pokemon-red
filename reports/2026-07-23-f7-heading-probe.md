# F7 — minimap-agnostic heading probe on banked MKDS frames (A3)

**Date:** 2026-07-23 · **Lane:** F7 (capability-map A3) · **Cost:** $0, offline, no paid run.
**Verdict:** heading recovery is **PLAUSIBLE but NOT demonstrated**; the banked frames are
**inadequate** for the accuracy measurement, and one **spacing-independent structural risk is
confirmed**. Do not build/wire anything. Next step is a free consecutive-frame capture (below).

## What A3 asks / what I probed
Capability map (A3, `reports/2026-07-05-northstar-capability-map.md:73-74`): a minimap-agnostic
heading primitive probed offline on banked MKDS frames — the rotating minimap kills the tile-grid
and continuous roll kills discrete facing (`runs/nds3d_probe/FINDINGS.md:340-372`). Question: can a
heading signal be recovered from the **top screen (viewport) only**, minimap excluded?

## Primitive check (perception-primitives first — no new code)
`core/yaw_flow.py:yaw_band_flow` already answers "am I turning, which way, how fast" (R0, numpy/PIL,
three-valued honesty: `"none"`=confidently-not-turning vs `None`=can't-tell). It **runs cleanly** on
256x192 MKDS top-screen input and emits calibrated confidence — no crash, no fabrication. The
primitive is applicable; the open question is whether MKDS *satisfies its preconditions*.

## Data reality (the first finding)
The banked probe (`runs/nds3d_probe/mkds_vision/race_measure/`) saved only **every 12th frame**;
`meta.json` holds scalar `pct_changed`, not frames. So **no consecutive frame pairs exist**, and
neither pass carries a **commanded-turn ground truth** (idle = no input; accel = A held, straight).
This is the identical blocker `eval/score_a3_precheck.py:20-30` documents for ViZDoom run3 ("no raw
frame pairs behind those rows"). Accuracy therefore **cannot be scored** on the banked data.

## Measured on the every-12th pairs (top screen, minimap dropped)
Ran `yaw_band_flow` on both passes at three 192-row bands (UPPER=horizon rows24-72,
MID=default-equiv 67-125, LOWER=kart 110-168) + the scaled multi-band vote.
- **Idle/countdown (camera static):** first 6 pairs → confident `dx=0 "none"`, prominence
  **0.44-0.98**. The primitive correctly reports "not turning" on a still scene.
- **Accel (forward motion — the case heading needs):** prominence **collapses to 0.02-0.12**
  (≈ the 0.02 floor); the three bands **disagree in sign on the same pair** (e.g. accel_f012:
  MID −16 "right", UPPER +41 "left", LOWER −60 "right"); the multi-band vote is **3/10 None** and
  sign-incoherent. No single `dx` describes the frame — the NCC surface is nearly flat.
- **Confound:** at 12-frame spacing, forward motion (~33%/frame, `FINDINGS.md:329`) far exceeds
  the band's usable shift, so this incoherence is partly sparsity, not purely model mismatch —
  which is exactly why it is inconclusive rather than a clean falsification.

## Confirmed structural risk (spacing-independent)
Per-frame horizon tilt (row of max vertical gradient, upper viewport) over the accel pass:
**−7.9° → −3.4° → +0.4° → +2.8° → −9.08°** — the horizon **rolls ~±9°** within one straight
segment. `yaw_band_flow` collapses a fixed-row band to a column-mean profile, which assumes the
horizon is a horizontal line; a ±9° roll smears that profile independent of frame spacing.
MKDS is a **high-angle chase-cam** (see the frames), not a first-person horizon world: forward
translation adds an **expansion/zoom flow** (left half streams left, right half streams right) on
top of yaw + roll. A 1D single-horizontal-translation model is a **genuine model mismatch** here,
not merely a tuning gap. (The "screen-locked kart pins NCC to 0" hypothesis was NOT supported —
the kart banks with the cam; static-frac in MID band = 0.0.)

## Recommendation
1. **Do not build or wire a heading primitive now**, and do not climb the Realizer Ladder — there
   is no measured failed bar yet (banked data can't produce one).
2. **Reroute the "cheapest probe":** the honest cheap next step is a **free consecutive-frame
   capture** from `mkds_race_start.state` with a scripted L/R steer and the commanded-turn logged
   as ground truth — the same instrumented-replay pattern `score_a3_precheck.py` already uses for
   ViZDoom. Small world-side script, $0, no new perception code; only that can measure feasibility.
3. **If that capture is run**, score two hypotheses the banked frames flagged: (a) does a net
   column-mean `dx` survive the expansion flow to encode turn sign; (b) does an **UPPER** (distant-
   horizon) band beat the ViZDoom-default MID band, since MKDS's clean-translation content sits
   high, not mid-screen. Pin a sign-agreement bar before running (gate-methodology).

## Falsifier status
A3 is falsified for this world class only if an R3 model on the **hot path** is required to read
heading. Not shown — R0 was never given adequate input. Boundary banked: **the banked MKDS frames
do not support a heading-accuracy measurement; a consecutive + ground-truthed capture is the gate.**

## Reproduction
`.venv-win/Scripts/python.exe` + `core.yaw_flow`; frames read-only from
`runs/nds3d_probe/mkds_vision/race_measure/*.png`, top 192 rows only (bottom 192 = minimap,
excluded); luminance gray; bands as above. Raw per-pair readings in this session's transcript.

## Sources
- `reports/2026-07-05-northstar-capability-map.md:62-76` (A3, cheapest probe, falsifier).
- `runs/nds3d_probe/FINDINGS.md:329,340-372` (idle 12.22%/frame; the three NDS perception breaks).
- `core/yaw_flow.py` (yaw_band_flow, three-valued contract, BAND/MAX_SHIFT/PROM_FLOOR).
- `eval/score_a3_precheck.py:20-30` (the no-retained-frame-pairs precedent + replay pattern).
