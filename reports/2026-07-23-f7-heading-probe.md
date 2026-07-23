# F7 — minimap-agnostic heading probe on banked MKDS frames (A3)

**Date:** 2026-07-23 · **Lane:** F7 (capability-map A3) · **Cost:** $0, offline, no paid run.
**Verdict:** heading recovery is **PLAUSIBLE but NOT demonstrated**; the banked frames are
**inadequate** for the accuracy measurement. A quantitative horizon-roll estimate on these frames
does **NOT** hold up under scrutiny (retracted below — region-choice-dependent, sign-unstable); the
expansion/zoom-flow model mismatch is the load-bearing structural risk. Do not build/wire anything;
next step is a free consecutive-frame capture (below).

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
  the band's usable shift, so this incoherence is partly sparsity, not a clean falsification.

## Horizon-roll claim: retracted (region-choice-dependent, sign-unstable)
An earlier pass claimed a **confirmed ±9° horizon roll** from a single "row of max vertical
gradient per column, upper viewport" linear fit — that does **not** survive scrutiny. Per-column
horizon-row picks scatter **std 20–34px** (residual std 17–34px after the fit), landing on
grandstand roofline/banners/crowd texture/the "LAP" HUD, not one horizon edge. The angle is **not
robust to region choice** (one pair: −9.4° full-width vs +7.6° right-HUD-dropped vs −17.6°
central-only) and **flips sign** on another pair when LAP-HUD columns drop (−5.2° → +22.2°). A
true roll is stable under those variations; this is a slope fit through track/grandstand/HUD noise.
**Retracted: horizon-roll on these frames is not a reliable heading signal.** The structural risk
that *does* hold is the expansion/zoom-flow mismatch measured above (UPPER/MID/LOWER disagree in
sign on the same pair) — needs no horizon measurement, and is the load-bearing part. ("Screen-locked
kart pins NCC to 0" was NOT supported — kart banks with the cam; static-frac in MID band = 0.0.)

## Recommendation
1. **Do not build or wire a heading primitive now** — no measured failed bar yet (banked data
   can't produce one); do not climb the Realizer Ladder.
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
