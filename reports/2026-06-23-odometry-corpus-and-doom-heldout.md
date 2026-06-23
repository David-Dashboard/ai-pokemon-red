# 2026-06-23 — Odometry corpus rebuild (locomotion-fixed) + Doom held-out zero-shot test

Follow-on to `reports/2026-06-23-camera-model-probe.md`. The camera-model probe diagnosed that 2D
camera-class separability was **corpus-limited**; a 4-agent workflow pinned the limiter to **locomotion
sparsity** (the jittery auto policy wiggled the avatar in place, so the camera never panned and the A3
translation-residual pinned ~1.0 for every game). This session fixed the data and added a 3D held-out test.

## TL;DR

- **Locomotion fix, two parts:** (1) new opt-in `record.py --explore` — a **direction-PERSISTENT** walk
  (`make_explore_action`, `--hold 16` ≥ one tile-step) so a follow/side camera actually scrolls; (2) **human
  play** (`--mode human`) for the games no auto policy can drive — side-scrollers need run+jump, and a held
  direction just walks them into a wall (verified: `--explore` got Kirby/Metroid stuck at 99% static / 97% menu).
- **`scrollPrev`** added to the probe — fraction of D-pad-moved transitions that are CLEAN camera pans
  (residual<0.7 & shift>thresh). It's the locomotion-robust cue the diagnosis recommended (the old A3 *median*
  washes out a minority of real scrolls).
- **Doom (ViZDoom `my_way_home`) added as a HELD-OUT game** (`dataset_split`), scored **zero-shot** against
  the 2D dev centroids in a new `held_out_test`.

## Corpus (dev = 7 units / 3 classes; Doom held-out). Data is gitignored — recipe in `eval/collect_corpus.md`.

| game (unit) | class | how recorded | A4_loc | scrollPrev |
|---|---|---|--:|--:|
| gold | follow_scroll | `--explore` from a human checkpoint | 1.00 | 21% |
| gauntlet | follow_scroll | human play | 0.86 | 30% |
| kirby | scroll_side | human play | 0.62 | 39% |
| metroid | scroll_side | human play | 0.61 | 58% |
| spaceinv | fixed | cold-boot `--smart-auto` | 0.19 | 2% |
| tetris | fixed | cold-boot `--smart-auto` | 0.09 | 0% |
| cavenoire | fixed | human play (single-screen → fixed) | 0.12 | 0% |
| **doom** (HELD-OUT) | fp3d | ViZDoom recorder (pose oracle) | — | — |

## Results

- **Cross-game per-frame sib-mean = 45%** (29% original → 43% → 45%). Modest — but the descriptive cue is clean:
  **`scrollPrev` separates SCROLL (21–58%) from FIXED (0–2%)** cleanly across unrelated games. Fixed games
  classify at 83–96%.
- **Follow-vs-side is confused** (follow→76% predicted side): both *scroll*; the per-frame centroid can't tell
  top-down 2-axis from horizontal 1-axis (that lives in `vshare`, noisy per-frame).
- **Held-out Doom (zero-shot):** `novelty ×1.3 → NOT flagged novel → assigned 'scroll_side'`. A 3D first-person
  **turn** produces horizontal optical flow that looks like a 2D side-scroll **pan**, so the cheap whole-frame
  centroid does not flag 3D as a new camera model. (The original probe flagged it novel ×2.3 only because its
  side-scroll data was junk; good side-scroll data made 3D-turn ≈ side-pan.) **But the 3D ego-motion signal is
  real** — pose-oracle anchor: turn L/R sign-separability **95%**, forward advance-corr **+0.47**.

## What this establishes / what's deferred

- **Established:** cheap pixels+buttons cues robustly tell **scrolling from fixed** cross-game; the locomotion
  fix (explore policy + human play) was the unlock; 3D ego-motion (turn/advance from optical flow) is real and
  oracle-verified.
- **Deferred ("re-fit later"):** (a) a **per-RUN** classifier using `scrollPrev`/`A4` as features (the current
  per-FRAME centroid is dominated by each scroller's non-scroll-majority frames); (b) **axis-aware** features to
  split follow vs side; (c) an **expansion/radial-flow** feature so 3D is flagged distinct from side-pan. The
  math is sound — these are feature/aggregation refinements, not bugs.

## Files
- `record.py` — opt-in `--explore` direction-persistent walk policy (`make_explore_action`).
- `eval/dataset_split.py` — Doom added to HELD-OUT; `is_heldout_run` now also matches the run-dir name (the
  ViZDoom recorder writes no meta ROM).
- `eval/probe_camera_model.py` — rebuilt corpus + corrected labels, `scrollPrev` signature column, `held_out_test`
  zero-shot section, leave-one-unit-out restricted to loaded dev runs.
