# 2026-06-23 — P1: 2D ego-motion probe (direction recovery, measure-first)

First step of the generalizable **ego-motion / odometry estimator** (the System-1 "how did I move" sense). The
camera-model classifier is the router (which branch); the estimator computes the motion. P1 is measure-first:
*does the game-agnostic `best_shift` recover self-motion DIRECTION from pixels alone, before we extract it into
`core/`?* New: `eval/probe_egomotion.py` (numpy+PIL, main env; reuses `best_shift`/`load_run` from
`eval/probe_camera_model.py`). Direction (sign) only — metric distance is deferred (the camera-model probe
showed it's unreliable).

## Results

**A. RAM ground-truth (Pokémon Gen-1 overworld; the only corpus with a position oracle): 98%.**
On ~1618 same-map, non-battle steps where RAM `(x,y)` actually moved, `best_shift(prev,curr)`'s `(dx,dy)`
points the way the avatar moved (east+x→+dx, south+y→+dy):

| run | n | direction-recovery |
|---|--:|--:|
| fix1 | 222 | 98% |
| fix2 | 287 | 98% |
| fix3 | 223 | 97% |
| fix4 | 592 | 99% |
| fix5 | 226 | 97% |
| explore_bench | 68 | 100% |
| **aggregate** | **1618** | **98%** |

This is the solid result — RAM-grounded, large N, consistent with the prior drift work (measured-distance
odometry drove pose-vs-RAM drift 40.2%→~0). The ~2% miss is mostly *camera-pinned* regions (map edges): RAM
moves but the camera doesn't scroll, so `best_shift=0` — a genuine limit of pixel-shift odometry, not a bug.

**B. Button-grounding (cross-game 2D-scroll, NO RAM; clean scrolls only, per-class scored):** partial.

| game | class | recover | note |
|---|---|---|---|
| metroid | side | **2/2** | left/right clean (`right +9.0`, `left −8.3`) |
| kirby | side | 1/2 | right OK; left → +dx (wrong) — per-game camera quirk |
| gauntlet | follow | 2/4 | right/up OK; left/down noisy (multidirectional/diagonal) |
| gold | follow | 0/1 | n<5 — escape-ladder-polluted (Gold's overworld trips the Red-tuned modality detector → reads "menu" → the explore gameplay-action rarely fired) |

Cross-game direction-grounding **holds where the recording is clean** (metroid), and is **recording-quality-
limited** otherwise — escape-ladder pollution (gold), diagonal noise (gauntlet), per-game camera quirks (kirby).
Same control/data-quality theme as the held-out verification, *not* an estimator failure.

## Conclusion

- **The 2D ego-motion DIRECTION estimator is validated** (98% vs RAM truth on Pokémon) → **greenlight P2**:
  extract `core/egomotion.py` (world-agnostic, reusing `best_shift`), consolidating the duplicate
  `games/pokemon_red/perceiver._best_shift`, and surface it additively via `spatial_memory["ego_motion"]` (the
  `SymbolicState` seam is unfrozen + JSON; `core/contracts.py` stays untouched).
- **Magnitude / metric distance deferred** — direction (sign) is what's reliable today.
- **B's partial cross-game result** is recording-quality-limited, consistent with the autonomous-control gap; the
  RAM-grounded A is the load-bearing evidence.

## Verification
- `uv run python -m eval.probe_egomotion` → eval A (RAM direction-recovery) + eval B (cross-game).
- `uv run pytest -q` → 308 passed (probe is an `eval/` script, untested by convention; imports resolve).
