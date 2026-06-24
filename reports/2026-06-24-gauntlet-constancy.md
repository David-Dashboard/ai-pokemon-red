# 2026-06-24 — Gauntlet II: the first CONSTANCY test (a second world, brain reused unchanged)

The biggest untested claim in the thesis — **"a new world swaps only the perceiver (+ a thin per-world
config); the brain is reused UNCHANGED"** — finally has a second world. We built a Gauntlet II perceiver +
plugin and ran the **existing** `ExploreBrain` / `Gateway` / `run_episode` against it. Nothing in `core/`
changed.

## What was built (all under `games/gauntlet/` + a thin driver)
- `games/gauntlet/perceiver.py` — pixels → `SymbolicState`, reusing `core.egomotion` (pose) + `core.modality`
  (`context`) and DROPPING all Pokémon-specific machinery (tile grid `_PLAYER_CELL`/`_TILE_PX`, place/warp
  graph, Gen-1 textbox font, `TileFunctionMap`). Pose = a coarse occupancy grid stepped one cell per confirmed
  move in the **ego-motion** direction (see the gate finding below).
- `games/gauntlet/{emulator,plugin}.py` — stripped copies of the Pokémon ones (no RAM-in-obs, no reward, no
  fade/warp, no battle settle). Perception-only: RAM, if a `watch` map is given, goes to `oracle.jsonl` for
  scoring ONLY, never into the agent's `Observation`.
- `games/gauntlet/__init__.py` — `GAUNTLET_SANDBOX` + a **thin** `GAUNTLET_SYSTEM` prompt (identity + controls
  + goal; no game-specific strategy — keeping it thin is the constancy result we want).
- `play_gauntlet.py` — a thin driver wiring the SAME core brains/gateway/runner to the Gauntlet plugin.

## Pose-drift gate finding (measure-first, before building)
`eval/probe_pose_drift.py` (merged, PR #8) showed the transferable pose recipe (occupancy grid stepped by
accumulated `ego_motion` direction) tracks the RAM oracle: Gauntlet net-heading 57→87%, warp-segmented drift
~0.09 (Pokémon positive control ~100% / 0.01–0.05; Kirby/Metroid break on 1D-scroll / room-warps = Phase 2).
The PACKAGED perceiver reproduces it (`eval/replay_gauntlet_pose.py`: 83% heading, 0.02 drift).
**Cross-game perceiver insight:** stepping the grid by the *commanded button* gave 0.31 drift — Gauntlet is
8-way, so a diagonal press drops one axis; stepping by the *ego-motion* direction (with walls still tracked in
commanded space) recovered 0.02. Command-space pose loses diagonals; ego-space pose doesn't.

## Live run (the constancy smoke, no API)
`play_gauntlet.py --brain scripted --steps 150` on the real ROM:
- 150 calls, **no crash**; the perceiver emitted a full `SymbolicState` every step.
- `detect_modality` read `gameplay`/`static`; pose dead-reckoned ([0,0]→[1,1]); `visited` grew 1→6;
  `moved`/`blocked` outcomes worked — the occupancy map builds from pixels on a second game.

## Constancy verdict — HOLDS (so far)
- **`core/` untouched** — `git status` shows changes ONLY under `games/gauntlet/` + the driver/eval/test files.
- **No RAM leak** — the watched registers (`x=0xC286,y=0xC2C6`) land in `oracle.jsonl`; the agent sees only
  pixel-derived `pose`/`context`/`ego_motion`. New fitness test `tests/test_gauntlet.py` extends the
  non-leaking-oracle wall to Gauntlet (RAM sentinels never surface in the obs).
- **Thin prompt** — `GAUNTLET_SYSTEM` is identity + controls + goal, same THINK/MOVE/GOTO contract as Pokémon;
  no Gauntlet strategy. The strong form of constancy (only surface config changes).

## Closed-loop finding: the camera dead-zone false-walls (+ the fix)

The offline pose gate passed (drift 0.02), but the closed loop exposed a perceiver bug the gate couldn't —
the same shape as the earlier Pokémon "offline metric overstates; closed-loop reveals the strand" lesson.

`ExploreBrain` (loaded from an autonomous gameplay checkpoint — `ScriptedBrain` mashes past the title, no
human) **navigated** (RAM-confirmed motion) but gave up early. Diagnosis across **5 runs / 4 maze starts**:
**95% of all `blocked` outcomes (70 of 74) were real moves the camera DEAD-ZONE hid** — the hero moved (RAM
changed) but the follow-camera didn't scroll (`best_shift≈0`), so the naive "no scroll ⇒ wall" idiom sealed
phantom walls and boxed the autopilot in. The brain did the right thing with a corrupted map → the bug is
PERCEIVER-side, not `core/`.

**It's general, not a Gauntlet quirk** (measured on the RAM-grounded recordings — no new perceivers needed):
fraction of real moves that are camera-static = **Gauntlet 24% / Metroid 19% / Kirby 9% / Pokémon ~0%**.
Pokémon is the immune outlier *because* it always centers the player — the only reason "no scroll ⇒ wall" has
worked for us. So this is a general flaw in that idiom for any non-centered camera.

**Fix (perceiver-side, `_WALL_CONFIRM=3`):** a true wall fails to scroll on *every* attempt; a dead-zone slide
is transient (the camera soon catches up = a move, which clears the count). So seal a wall only after N
persistent no-scroll attempts from the same cell+direction. Validated on the same 5 checkpoints: real-world
traversal (RAM span) up in **all 5** runs, total moves **129→223 (+73%)**, phantom walls **70→42 (−40%)**.
Not fully eliminated (the dead-zone is a fundamental pixels-only limit; `_WALL_CONFIRM` is a coverage/accuracy
dial). **CORE-PROMOTION CANDIDATE:** the robustness is general — lift it to a shared `core/` perceiver helper
when a 2nd world's perceiver needs it (Pokémon, always-centered, does not).

## Open / next (logged, not silently worked around)
- **Stronger demo:** `ScriptedBrain` mashes through the title but explores little. The `ExploreBrain`
  navigation demo (brain's pathfinder driving the maze, reading the perceiver's map) needs a **gameplay
  save-state** to start past Gauntlet's title/hero-select (the autopilot only moves, so it can't pass the
  intro) — the same "hard scripted intro" residual seen in Pokémon name-entry. Capture a `--window` checkpoint
  once, then `--brain explore`.
- **8-way exploration** via a 4-cardinal `ExploreBrain` is a constancy risk to WATCH (don't edit `core/`): if
  cardinals explore too slowly, the fix is prompt-driven diagonal sequences from the LLM, not a core edit.
- Side-scrollers (Kirby/Metroid) remain Phase 2 (a different pose model + timing control).

## Verification
- `eval/replay_gauntlet_pose.py` → perceiver pose vs RAM oracle (83% / 0.02).
- `play_gauntlet.py --brain scripted` → end-to-end loop on the ROM, `core/` untouched.
- `uv run pytest -q` → green incl. `tests/test_gauntlet.py` (no-leak wall + perceiver smoke).
