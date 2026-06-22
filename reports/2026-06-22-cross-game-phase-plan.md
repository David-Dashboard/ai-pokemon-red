# Cross-game perception-generalization — phase plan

**Branch:** `feat/cross-game-perception` (off `feat/novelty-signal`, which carries the tile-map /
perceiver / `cross_game.py` this builds on). **Goal:** prove (or break) that the core + the brain
generalize across games by running them against a *ladder* of GB games with different camera/view
models. **Success metric: how LITTLE the brain (decision-taking) has to change** as we climb the ladder.

## What varies per game (the perceiver = the swap point) vs the invariant
- **Per-game (perceiver / World-Interface):** self-localization/**odometry** (camera model — the biggest
  varier), **affordance perception** + its vocabulary (walkable/blocked vs ground/gap/hazard),
  mode-detection, OCR font, entity-detection, **action/motion contract** (move vs jump/attack).
- **Invariant (we protect these):** the System-2 brain (aria: goals, reasoning, identity — game-specifics
  live in its per-world *constitution*, not new code), the core learning machinery (behaviour=truth,
  novelty, advisory+veto), and the `SymbolicState` seam. Partly per-genre: the System-1 controller
  (frontier-explore is top-down-only; platformers need their own).

## Data-collection strategy (the key principle)
**Record the RAW, game-agnostic substrate** — `(frame_t, exact buttons pressed, frame_t+1, optional RAM)`
— and **defer ALL odometry/labeling to offline replay.** Do NOT bake today's Pokémon perceiver
(camera-scroll, player-at-(4,4)) into the data; it's wrong for Zelda/Kirby. Raw triples let us develop
and *re-develop* any odometry offline and relabel without re-collecting. Drive it: human play (deep, any
game) · random/auto policy (free breadth, no perceiver needed) · per-game start-states (skip intros).

## Build sequence
1. **Generalized RAW recorder** (game-agnostic, no Pokémon perceiver) — THE unblocking tool. Any GB ROM →
   `frames/` + a `buttons.jsonl` of `{step, frame, buttons, ram?}`. Human (SDL window, capture real
   buttons) + random-auto modes. Sampling at settled/per-input cadence.
2. **Collect** on what we have (Gold, Kirby) + the acquisition ladder (Lolo → Zelda Oracle → …).
3. **Generalizable self-localization/odometry** (offline, against the raw corpus): detect the camera
   model (follow-scroll / static-sprite / forced-scroll / fixed) and estimate self-motion accordingly —
   the core per-game-varying piece. Reuse `saliency.py` (find the moving sprite) for the static-camera case.
4. **Per-game perceiver** = core odometry + the (agnostic) `TileFunctionMap` + per-game extraction
   (mode/OCR/entities). Validate the `SymbolicState` it emits matches the frozen seam.
5. **Cross-game verdict** (`eval/cross_game.py`): build the tile-map on game A, test on game B — does
   appearance→function **fail safe** (low coverage = novel→explore) on a never-seen game, or confidently
   mispredict? This is the generalization headline.

## Acquisition ladder
See `reports/2026-06-22-gb-perception-test-suite.md` (web-verified): Lolo (fixed-screen) → Zelda Oracle
(flip-screen) → FF Adventure (flip+real-time) → Crystalis (real-time 8-way) → Metroid II (side-view 2D) →
Q*bert (iso) → F-1 Race (pseudo-3D) → Sword of Hope II (first-person). We own Red/Gold/Zelda-LA/Kirby.

## 3D — now IN scope this iteration (via a cheap gate; David's call)
Rather than defer 3D blindly, we probe it cheaply NOW and let the result gate a full 3D iteration:
- **Mechanism:** `eval/vizdoom_smoke.py` (ViZDoom `my_way_home`) tests whether behaviour=truth + a cheap
  pixels-only self-motion signal survives 3D ego-motion. ViZDoom gives ground-truth position (the 3D
  analog of GB RAM). **Preliminary:** frame-diff separates advanced-vs-blocked-by-wall at 83.7%
  (baseline 67.8%) — looks positive; under adversarial verification.
- **Gate rule:** if it HOLDS → GREENLIGHT It3 (real 3D on ViZDoom — optical-flow odometry + a 3D spatial
  representation, NOT the tile→function grid) as the next iteration. If it COLLAPSES → 3D is a clean-sheet
  perceiver, budgeted as its own iteration.
- The 2D GB ladder stays THIS iteration's primary axis; 3D is the gated next rung. The GB pseudo-3D / FP /
  iso games (F-1, Sword of Hope, Q*bert) remain the free 3D-adjacent proxies.

## Held-out verification split (anti-overfitting — `eval/dataset_split.py`)
**HARD RULE: never develop/tune/calibrate against the HELD-OUT games; touch them only at final
verification (`cross_game.py --test`).** One game per axis (dev keeps an example of each):
- **Held-out:** Crystalis (follow / real-time-8way) · Zelda LA (flip) · Super Mario Land (side; ROM TBD) ·
  F-1 Race (pseudo-3D).
- **Dev (9):** Pokémon Red, Pokémon Gold, Gauntlet II · FF Adventure, Cave Noire · Kirby, Metroid II ·
  Sword of Hope II, Tetris Plus.
- Open fork: holding out Zelda is the most honest flip test; alternatively dev on Zelda and hold out
  Cave Noire. Editable in `eval/dataset_split.py`.

## Status
Branch created + prepared; generalized recorder BUILT (`record.py`). Auto-collected (dev): Kirby×2,
Metroid II×2, Gauntlet II. Need a human nudge into gameplay (intro/name-entry): Gold, FF Adventure,
Cave Noire, Sword of Hope, Tetris (dev) + Zelda, Crystalis, F-1 (held-out — data ok, just don't tune).
**NEXT = build the generalizable odometry (camera-model detection) OFFLINE against the DEV corpus.**
