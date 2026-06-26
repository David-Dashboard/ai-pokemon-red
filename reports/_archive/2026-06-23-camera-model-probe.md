# 2026-06-23 — Camera-model probe (offline, cheap, button-grounded)

**What it tested:** whether cheap, pixels-only motion signals — grounded by the recorded BUTTON log — can
tell which **camera model** a game uses, on a game never tuned on. This is the *measure-first* step before
building a generalizable odometry / ego-motion estimator (the System-1 "how did I move" sense). Free/offline,
numpy+PIL only, run in the main `uv` env: `uv run python -m eval.probe_camera_model`.

New code: [`eval/probe_camera_model.py`](../eval/probe_camera_model.py). Reuses the ViZDoom optical-flow
proxies from [`eval/vizdoom_flow_ceiling.py`](../eval/vizdoom_flow_ceiling.py) and generalizes
`games/pokemon_red/perceiver._best_shift` (kept game-agnostic in the probe — no `games/` import).

DEV corpus (7 runs, one–two games per camera class): red_random1 + red_smart1 (top-down), kirby_auto1 +
metroid_auto1 (side-scroll), spaceinv_smart1 + gauntlet_auto1 (labeled "fixed" — see below), vizdoom_mywayhome
(first-person 3D, with `pos`/`angle` as a **non-leaking oracle** used only to VALIDATE, never as a feature).

**Timing correctness (the off-by-one that wrecked the early ViZDoom smoke test):** the GB recorder saves
`frame_i` AFTER applying `act_i`, so transition `(i-1 → i)` is caused by `buttons[i]`; the ViZDoom recorder
logs pose+buttons BEFORE acting, so its `(i-1 → i)` is caused by `buttons[i-1]`. The probe applies the correct
timing per source — otherwise A2 (sign) is garbage.

## TL;DR

- ✅ **3D ego-motion signatures are REAL and oracle-verified.** Turn direction from column-shift sign:
  **95% L/R separability** (in-sample, ≥50% by construction — the convincing evidence is the per-class flow_x
  mean gap: TURN_LEFT −10.79 vs TURN_RIGHT +14.45). Forward advance vs expansion-flow: **corr +0.42** against
  ground-truth position change. Reproduces the prior flow-ceiling result. (Whole-frame frame-diff alone *cannot*
  tell rotation from translation; column-shift sign + radial expansion can.)
- ✅ **The per-game button-grounded SIGNATURES are interpretable and mostly correct** where the recording is
  real gameplay (the descriptive core — see table).
- ⚠️ **Cross-game camera-CLASS classification is NOT yet demonstrated** (sibling-class mean per-frame acc 44%,
  over the only classes spanning ≥2 different games: side kirby↔metroid, fixed spaceinv↔gauntlet).
  The probe is a sound instrument; the limiter is the CORPUS, and the probe told us exactly how:
  (1) a class-label error, (2) non-gameplay recordings, (3) too few games per class.

## Per-game signature table (button-grounded)

| game | class | A1_fd | A2_coup | vshare | A3_res | A4_loc |
|---|---|--:|--:|--:|--:|--:|
| red_random1 | scroll_topdown | 0.0 | **0.89** | 0.46 | **0.47** | 0.36 |
| red_smart1 | scroll_topdown | 8.6 | nan | 0.93 | 1.00 | 0.36 |
| kirby_auto1 | scroll_side | 0.0 | **1.00** | **0.00** | 1.00 | 0.08 |
| metroid_auto1 | scroll_side | 0.1 | 0.59 | 0.70 | 0.94 | 0.37 |
| spaceinv_smart1 | fixed | 6.1 | nan | 0.96 | 1.00 | **0.19** |
| gauntlet_auto1 | fixed | 0.3 | 0.45 | 0.14 | 0.60 | **0.86** |

A1_fd = idle motion (no button). A2_coup = D-pad→shift consistency (0..1, hi=camera scroll). vshare = vertical
share of scroll (hi=top-down, lo=side). A3_res = best-2D-translation residual (lo=rigid scroll). A4_loc =
fraction of frame that moved (hi=global/scroll, lo=local/fixed).

## What worked

- **3D is the strong, verified result** (above). The cheap optical-flow ego-motion classifier (turn-L / turn-R /
  advance) is real and grounded against the pose oracle. 3D odometry-as-a-discrete-classifier has legs.
- **Features carry the 2D signal where gameplay is real.** `red_random1` reads as a rigid top-down scroller
  (A3=0.47, A2=0.89, balanced vshare); `spaceinv` reads as truly fixed (A4=0.19, A2=nan — no camera scroll);
  `kirby` where it scrolls is pure-horizontal (vshare=0.00, A2=1.00) — a textbook side-scroller cue.

## What broke / what the probe exposed (the value of this run)

- **My a-priori camera-class label for Gauntlet was WRONG.** A4=0.86 (whole-frame motion) ⇒ Gauntlet II is a
  multidirectional **follow-scroller**, not fixed-screen (cf. truly-fixed Space Invaders A4=0.19). The data
  corrected the taxonomy. "fixed" conflated two different camera models.
- **`red_smart1` is a polluted top-down example** — A2=nan / A3=1.00 / A1_fd=8.6 = stuck in Red's intro/menus
  (the known "smart-auto can't crack a hard scripted intro"), not overworld walking.
- **`kirby_auto1` exercises little sustained scroll** (A4=0.08) — the cold-boot auto policy doesn't run far,
  so its signature is unreliable despite the correct cue when it does scroll.
- **Result:** leave-one-UNIT(game)-out camera-class separability is weak (sib-mean **44%** over the classes that
  span ≥2 different games — spaceinv/gauntlet both predict "fixed" 77%/72%, but that's the mislabeled pair
  agreeing with itself; kirby→top-down 0%, metroid→fixed 28%). Singletons (top-down=pokemon, 3d=vizdoom) MUST
  miss by construction (no same-class training game) → reported as novelty: the **3d singleton lands far from all
  known centroids (novelty ×2.3) = correctly flagged as a NEW camera model**, but the **top-down singleton does
  NOT (novelty ×1.0)** — Pokémon's rigid-scroll motion overlaps the 2D-scroll/fixed feature space, so it blends
  in rather than flagging novel (honest negative; a finer feature or a 2nd top-down game would be needed).
- **Methodology fix (caught in review of PR #2):** the hold-out is leave-one-**UNIT**-out, not per-run —
  `red_random1`/`red_smart1` are the **same game** (Pokémon), so counting them as two cross-game units folded
  same-game memorization into the mean (the earlier 31% mislabeled topdown as having a "sibling"). Pokémon is now
  one unit (mirrors the appearance probe's `UNIT` dict), so the cross-game mean covers exactly side+fixed and
  topdown is correctly a singleton. This compounds at the rebuilt corpus (Red + Gold are both Pokémon → still one
  domain for top-down).
- **Root cause is the corpus, not the features:** ≤2 games/class (three singletons after de-duping Pokémon),
  recording quality, and the label error. A naive cross-game centroid classifier can't extract a clean class from
  this; the per-game signatures can.

## Honest scope

7 runs, 1–2 games/class, ~300 transitions each; frames normalized to 128×112 (ViZDoom aspect distorted).
Decisive on THESE units only — not the held-out four (Zelda-LA / SML / Crystalis / F-1, never loaded; leakage
guard `eval/dataset_split.is_heldout_run` applied).

## Next

The probe is the ready instrument; the **odometry CORPUS** is the gate to a real separability verdict, now with
concrete requirements this run defined:
1. **Sustained-gameplay recordings**, gated by `eval/corpus_activity.py` (drop menu/intro-polluted runs like
   `red_smart1`; checkpoint-resume the RPGs so they're in real gameplay).
2. **≥2–3 games per camera class** (esp. a 2nd truly-fixed game and, eventually, a 2nd 3D scenario) so cross-game
   class-ID is even testable for every class, not just scrollers.
3. **Correct camera-class labels** (Gauntlet = follow-scroll; reconsider the 2D taxonomy as camera-MOTION-type
   {fixed / rigid-2D-scroll / nonrigid-3D-flow}, which is what odometry actually needs to branch on).
Then re-run `eval/probe_camera_model.py` for the cross-game separability verdict.

<!-- Per-run Definition of Done: (1) report (this file) (2) sections filled, oracle-grounded (3) LEARNINGS
bullet (4) HANDOFF §2 + current-status memory. -->
